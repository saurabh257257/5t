"""
Background scheduler — auto-snapshots SENSEX option chain every 1 minute
during market hours, stores AI summary to SQLite. No login required.
Also runs S/R proximity monitor at configurable intervals.
"""
import json
import os
import anthropic as _anthropic
from datetime import datetime, timezone, timedelta

from modules.auth import _restore_client
from modules.market import get_expiry_dates, get_option_chain_data, get_index_ltp
from modules.db import (save_snapshot, cleanup_old_snapshots,
                        get_sr_history, save_sr_alert, was_recently_alerted,
                        get_setting, cleanup_old_alerts)
from modules.telegram import send_sr_alert, send_message

_IST = timezone(timedelta(hours=5, minutes=30))


def _is_market_hours():
    """True if current IST time is within NSE/BSE trading hours, Mon–Fri."""
    now = datetime.now(_IST)
    if now.weekday() >= 5:          # Saturday=5, Sunday=6
        return False
    market_open  = now.replace(hour=9,  minute=14, second=0, microsecond=0)
    market_close = now.replace(hour=15, minute=31, second=0, microsecond=0)
    return market_open <= now <= market_close


def run_sensex_snapshot():
    """
    Fetch SENSEX nearest-expiry option chain, generate AI summary, save to DB.
    Called every 1 minute by APScheduler. Uses saved JWT — no browser needed.
    """
    print('[SCHEDULER] run_sensex_snapshot called', flush=True)
    if not _is_market_hours():
        print('[SCHEDULER] Outside market hours, skipping', flush=True)
        return

    try:
        # ── 1. Restore 5paisa client from saved session ───────────────────────
        client = _restore_client()
        if not client:
            print('[SCHEDULER] No saved session — log in once via the dashboard')
            return

        # ── 2. Get nearest expiry ─────────────────────────────────────────────
        expiry_data = get_expiry_dates(client, 'B', 'SENSEX')
        if 'error' in expiry_data or not expiry_data.get('expiries'):
            print('[SCHEDULER] Could not fetch SENSEX expiries')
            return

        expiry     = expiry_data['expiries'][0]       # nearest expiry
        expiry_ts  = expiry['ts']
        expiry_lbl = expiry['label']

        # ── 3. Live index data ────────────────────────────────────────────────
        ltp_data   = get_index_ltp(client, 'B', 999901, 'SENSEX')
        ltp        = ltp_data.get('ltp', 0)
        prev_close = ltp_data.get('prev_close', 0)
        change_abs = ltp_data.get('change', 0)
        change_pct = ltp_data.get('change_pct', 0)

        if ltp == 0:
            print('[SCHEDULER] SENSEX LTP = 0, skipping')
            return

        # ── 4. Option chain ───────────────────────────────────────────────────
        chain = get_option_chain_data(client, 'B', 'SENSEX', expiry_ts)
        if 'error' in chain or not chain.get('option_chain'):
            print('[SCHEDULER] No option chain data')
            return

        rows        = chain['option_chain']
        total_ce_oi = sum(r['ce_oi'] for r in rows)
        total_pe_oi = sum(r['pe_oi'] for r in rows)
        pcr         = round(total_pe_oi / total_ce_oi, 2) if total_ce_oi > 0 else 0
        max_pain    = max(rows, key=lambda r: r['ce_oi'] + r['pe_oi'],
                         default={'strike': 0})['strike']

        top_ce    = sorted(rows, key=lambda r: r['ce_oi'],  reverse=True)[:3]
        top_pe    = sorted(rows, key=lambda r: r['pe_oi'],  reverse=True)[:3]
        near_rows = sorted(rows, key=lambda r: abs(r['strike'] - ltp))[:12]

        chain_txt = 'Strike|CE_OI|CE_ChgOI|PE_OI|PE_ChgOI\n'
        for r in near_rows:
            chain_txt += (f"{int(r['strike'])}|{r['ce_oi']}|{r['ce_chg_oi']}"
                          f"|{r['pe_oi']}|{r['pe_chg_oi']}\n")

        # ── 5. AI summary ─────────────────────────────────────────────────────
        prompt = f"""SENSEX option chain snapshot. Be brief and direct.

Price: {ltp} | Change: {change_abs:+.0f} ({change_pct:+.2f}%) | Expiry: {expiry_lbl}
PCR: {pcr} | Max Pain: {int(max_pain)}
Top CE resistance: {', '.join(str(int(r['strike'])) for r in top_ce)}
Top PE support: {', '.join(str(int(r['strike'])) for r in top_pe)}

{chain_txt}

In 80 words max: (1) Bias bullish/bearish/neutral + reason, (2) Key support level, (3) Key resistance level, (4) Watch out for."""

        ac  = _anthropic.Anthropic()
        rsp = ac.messages.create(
            model='claude-haiku-4-5', max_tokens=250,
            messages=[{'role': 'user', 'content': prompt}]
        )
        summary = rsp.content[0].text.strip()

        # ── 6. Save to DB ─────────────────────────────────────────────────────
        save_snapshot(
            index_id='SENSEX', expiry_label=expiry_lbl, expiry_ts=expiry_ts,
            ltp=ltp, prev_close=prev_close, change_abs=change_abs,
            change_pct=change_pct, pcr=pcr, max_pain=max_pain,
            ce_oi=total_ce_oi, pe_oi=total_pe_oi, summary=summary,
        )

        # Keep only last 7 days
        cleanup_old_snapshots(days=7)

        now_str = datetime.now(_IST).strftime('%H:%M:%S')
        print(f'[SCHEDULER] SENSEX snapshot saved @ {now_str} | LTP={ltp} | PCR={pcr}')

        # Send Telegram alert
        direction = '▲' if change_abs >= 0 else '▼'
        msg = (
            f'📊 <b>SENSEX Snapshot — {now_str} IST</b>\n\n'
            f'<b>LTP:</b> ₹{ltp:,.2f} {direction} {change_abs:+.0f} ({change_pct:+.2f}%)\n'
            f'<b>Expiry:</b> {expiry_lbl}\n'
            f'<b>PCR:</b> {pcr} | <b>Max Pain:</b> ₹{int(max_pain):,}\n\n'
            f'<b>AI Summary:</b>\n{summary}'
        )
        send_message(msg)

    except Exception as e:
        print(f'[SCHEDULER] Error in run_sensex_snapshot: {e}')


# ── S/R Proximity Monitor ──────────────────────────────────────────────────────

def run_sr_monitor():
    """
    Check SENSEX + NIFTY LTP against stored S/R levels.
    Fires Telegram alert when within threshold%. Runs at configurable interval.
    Runs any time (not restricted to market hours) so you can monitor pre/post market.
    """
    if get_setting('sr_monitor_enabled', 'true') != 'true':
        return

    threshold_pct = float(get_setting('sr_threshold_pct', '0.3'))

    client = _restore_client()
    if not client:
        return

    # Load all configured indices from indices.json
    try:
        _idx_file = os.path.join(os.path.dirname(__file__), '..', 'indices.json')
        with open(_idx_file) as f:
            all_indices = json.load(f)
    except Exception:
        all_indices = [
            {'id': 'SENSEX', 'feed_exch': 'B', 'feed_scrip': 999901},
            {'id': 'NIFTY',  'feed_exch': 'N', 'feed_scrip': 999920},
        ]

    for idx in all_indices:
        try:
            _check_sr_proximity(client, idx['id'], idx['feed_exch'],
                                idx['feed_scrip'], threshold_pct)
        except Exception as e:
            print(f'[SR_MONITOR] Error for {idx["id"]}: {e}')

    cleanup_old_alerts(days=30)


def _check_sr_proximity(client, index_id, exch, scrip, threshold_pct):
    """For one index: fetch LTP, compare to stored S/R levels, alert if close."""
    ltp_data = get_index_ltp(client, exch, scrip, index_id)
    ltp      = ltp_data.get('ltp', 0)
    if ltp == 0:
        return

    history = get_sr_history(index_id, limit=1)
    if not history:
        return

    latest = history[0]
    levels = (
        [{'level': float(s['level']), 'type': 'support'}
         for s in latest.get('supports', [])] +
        [{'level': float(r['level']), 'type': 'resistance'}
         for r in latest.get('resistances', [])]
    )

    for entry in levels:
        level    = entry['level']
        dist_pct = abs(ltp - level) / level * 100
        if dist_pct <= threshold_pct:
            if not was_recently_alerted(index_id, level, minutes=30):
                save_sr_alert(index_id, level, entry['type'], ltp, dist_pct)
                send_sr_alert(index_id, level, entry['type'], ltp, dist_pct)
                now_s = datetime.now(_IST).strftime('%H:%M:%S')
                print(f'[SR_MONITOR] {index_id} @ {ltp} near {entry["type"]} '
                      f'{level} ({dist_pct:.3f}%) @ {now_s}')

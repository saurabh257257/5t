"""
Background scheduler — auto-snapshots SENSEX option chain every 1 minute
during market hours, stores AI summary to SQLite. No login required.
"""
import anthropic as _anthropic
from datetime import datetime, timezone, timedelta

from modules.auth import _restore_client
from modules.market import get_expiry_dates, get_option_chain_data, get_index_ltp
from modules.db import save_snapshot, cleanup_old_snapshots

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
    if not _is_market_hours():
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

    except Exception as e:
        print(f'[SCHEDULER] Error in run_sensex_snapshot: {e}')

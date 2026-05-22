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
from modules.market import get_expiry_dates, get_option_chain_data, get_index_ltp, get_today_ohlc, get_ltp
from modules.db import (save_snapshot, cleanup_old_snapshots,
                        get_sr_history, get_setting, set_setting,
                        get_pending_watchlist, update_watchlist_executed, update_watchlist_failed,
                        get_watchlist, update_watchlist_exit)
from modules.telegram import send_message

_IST = timezone(timedelta(hours=5, minutes=30))

_LOT_SIZES  = {'SENSEX': 20, 'NIFTY': 65, 'BANKNIFTY': 30, 'FINNIFTY': 30}
_SL_OFFSETS = {'SENSEX': 150, 'NIFTY': 47, 'BANKNIFTY': 45, 'FINNIFTY': 45}

_TICK = 0.05   # BSE/NSE options tick size

def _t(price):
    """Round price to nearest 0.05 tick (required by exchange for option orders)."""
    return round(round(float(price) / _TICK) * _TICK, 2)

def _lot_qty(index_id, lots):
    """Convert lots → actual qty using index lot size."""
    return int(lots) * _LOT_SIZES.get(index_id, 1)


def _place_sl_order(client, index_id, scrip_code, exch, entry_price, actual_qty):
    """
    Place a stop-loss sell order immediately after a buy is confirmed.
    SL offset: SENSEX=150 pts, others=45 pts (per-option-premium points).
    """
    sl_offset  = _SL_OFFSETS.get(index_id, 150)
    sl_trigger = _t(max(entry_price - sl_offset, 0.05))
    sl_limit   = _t(max(sl_trigger - 2, 0.05))   # limit price 2 below trigger
    try:
        result = client.place_order(
            OrderType='S', Exchange=exch, ExchangeType='D',
            ScripCode=scrip_code, Qty=actual_qty,
            Price=sl_limit, StopLossPrice=sl_trigger,
            IsIntraday=True, IsIOCOrder=False,
        )
        print(f'[SL_ORDER] {index_id} trigger={sl_trigger} limit={sl_limit} qty={actual_qty} → {result!r}')
        return result, sl_trigger
    except Exception as e:
        print(f'[SL_ORDER] Failed to place SL order: {e}')
        return None, sl_trigger


def _is_market_hours():
    """True if current IST time is within NSE/BSE trading hours, Mon–Fri."""
    now = datetime.now(_IST)
    if now.weekday() >= 5:          # Saturday=5, Sunday=6
        return False
    market_open  = now.replace(hour=9,  minute=14, second=0, microsecond=0)
    market_close = now.replace(hour=15, minute=31, second=0, microsecond=0)
    return market_open <= now <= market_close


def _in_trading_window():
    """True if IST time is 9:00 AM – 3:30 PM, Mon–Fri."""
    from datetime import time as _t
    now = datetime.now(_IST)
    if now.weekday() >= 5:
        return False
    t = now.time()
    return _t(9, 0) <= t <= _t(15, 30)


def _check_market_hours_gate(setting_key):
    """Return False (skip job) if market-hours filter is ON and we're outside window."""
    if get_setting(setting_key, 'false') == 'true' and not _in_trading_window():
        print(f'[SCHEDULER] {setting_key} gate: outside market hours, skipping', flush=True)
        return False
    return True


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

    except Exception as e:
        print(f'[SCHEDULER] Error in run_sensex_snapshot: {e}')


# ── Market Update ──────────────────────────────────────────────────────────────

def _load_indices_cfg():
    """Load all indices from indices.json relative to this file."""
    try:
        _idx_file = os.path.join(os.path.dirname(__file__), '..', 'indices.json')
        with open(_idx_file) as f:
            return json.load(f)
    except Exception:
        return [
            {'id': 'SENSEX',    'label': 'SENSEX',    'feed_exch': 'B', 'feed_scrip': 999901, 'chart_exch': 'B', 'chart_scrip': 999901},
            {'id': 'NIFTY',     'label': 'NIFTY 50',  'feed_exch': 'N', 'feed_scrip': 999920, 'chart_exch': 'N', 'chart_scrip': 999920000},
            {'id': 'BANKNIFTY', 'label': 'BANK NIFTY','feed_exch': 'N', 'feed_scrip': 999921, 'chart_exch': 'N', 'chart_scrip': 999920005},
            {'id': 'FINNIFTY',  'label': 'FIN NIFTY', 'feed_exch': 'N', 'feed_scrip': 999922, 'chart_exch': 'N', 'chart_scrip': 999920041},
        ]


def run_market_update():
    """
    Send a combined Telegram message with LTP, OHLC, and nearest S/R levels
    for all 4 indices. Runs at configurable frequency (default 5 min).
    """
    if get_setting('market_update_enabled', 'false') != 'true':
        return
    if not _check_market_hours_gate('market_update_market_hours'):
        return

    print('[MARKET_UPDATE] run_market_update called', flush=True)

    from modules.auth import _restore_client
    client = _restore_client()
    if not client:
        print('[MARKET_UPDATE] No saved session — skipping')
        return

    all_indices  = _load_indices_cfg()
    enabled_ids  = set(get_setting('market_update_indices', 'SENSEX,NIFTY,BANKNIFTY,FINNIFTY').split(','))
    now_str      = datetime.now(_IST).strftime('%H:%M')
    lines        = [f'📈 <b>Market Update — {now_str} IST</b>']

    for idx in all_indices:
        if idx['id'] not in enabled_ids:
            continue
        try:
            index_id = idx['id']
            label    = idx.get('label', index_id)

            # Fetch LTP + prev_close + change (chart_scrip for correct historical)
            ltp_data   = get_index_ltp(client, idx['feed_exch'], idx['feed_scrip'], idx.get('opt_symbol'),
                                       chart_scrip=idx.get('chart_scrip', idx['feed_scrip']))
            ltp        = ltp_data.get('ltp', 0)
            prev_close = ltp_data.get('prev_close', 0)
            change     = ltp_data.get('change', 0)
            change_pct = ltp_data.get('change_pct', 0)
            if ltp == 0:
                print(f'[MARKET_UPDATE] {index_id} LTP=0, skipping')
                continue

            direction = '▲' if change_pct >= 0 else '▼'
            sign      = '+' if change >= 0 else ''

            # Fetch today's OHLC using chart_exch / chart_scrip
            ohlc_line = ''
            try:
                c_exch  = idx.get('chart_exch', idx['feed_exch'])
                c_scrip = idx.get('chart_scrip', idx['feed_scrip'])
                ohlc = get_today_ohlc(client, c_exch, c_scrip)
                if 'error' not in ohlc:
                    o = int(ohlc.get('open', 0))
                    h = int(ohlc.get('high', 0))
                    l = int(ohlc.get('low',  0))
                    ohlc_line = f'O:{o:,} H:{h:,} L:{l:,}'
            except Exception as oe:
                print(f'[MARKET_UPDATE] {index_id} OHLC error: {oe}')

            # Nearest S/R
            sup_line = ''
            res_line = ''
            try:
                history = get_sr_history(index_id, limit=1)
                if history:
                    latest      = history[0]
                    supports    = [float(s['level']) for s in latest.get('supports', [])]
                    resistances = [float(r['level']) for r in latest.get('resistances', [])]
                    # Nearest support BELOW ltp
                    below_sups = [s for s in supports if s < ltp]
                    if below_sups:
                        nearest_sup = max(below_sups)
                        sup_dist    = abs(ltp - nearest_sup) / nearest_sup * 100
                        sup_line    = f'🛡️ S: {int(nearest_sup):,} ({sup_dist:.2f}% away)'
                    # Nearest resistance ABOVE ltp
                    above_res = [r for r in resistances if r > ltp]
                    if above_res:
                        nearest_res = min(above_res)
                        res_dist    = abs(nearest_res - ltp) / nearest_res * 100
                        res_line    = f'🚧 R: {int(nearest_res):,} ({res_dist:.2f}% away)'
            except Exception as sre:
                print(f'[MARKET_UPDATE] {index_id} S/R error: {sre}')

            # Build block for this index
            block = f'\n<b>{label}</b>: ₹{ltp:,.2f} {direction} {sign}{change:.0f} ({sign}{change_pct:.2f}%)'
            if prev_close > 0:
                block += f'\nPrev close: ₹{prev_close:,.2f}'
            if ohlc_line:
                block += f'\n{ohlc_line}'
            if sup_line or res_line:
                block += f'\n{sup_line}  {res_line}'.rstrip()
            lines.append(block)

        except Exception as e:
            print(f'[MARKET_UPDATE] Error for {idx.get("id","?")}: {e}')

    # Append pending watchlist conditions
    try:
        pending = get_pending_watchlist()
        if pending:
            wl_lines = ['\n📌 <b>Watchlist Tracking</b>']
            for w in pending:
                cond = '≥' if w['trigger_condition'] == 'above' else '≤'
                wl_lines.append(
                    f"• <b>{w['index_id']}</b> BUY {w['strike']} {w['option_type']} "
                    f"@ ₹{w['premium']} — enter when {w['index_id']} {cond} {int(w['trigger_price']):,} "
                    f"| SL ₹{w['sl']} | Tgt ₹{w['target']}"
                )
            lines.extend(wl_lines)
    except Exception as _we:
        print(f'[MARKET_UPDATE] watchlist section error: {_we}')

    if len(lines) > 1:
        send_message('\n'.join(lines))
        set_setting('market_update_last_sent', datetime.now(_IST).strftime('%Y-%m-%d %H:%M:%S'))
        print(f'[MARKET_UPDATE] Sent update for {len(lines)-1} indices @ {now_str}')
    else:
        print('[MARKET_UPDATE] No data to send')


# ── Trade Watchlist Watcher ────────────────────────────────────────────────────

def run_trade_watcher():
    """
    Every 2 minutes during market hours: check pending watchlist items.
    If an index crosses its trigger_price, place a limit order automatically.
    """
    if not _is_market_hours():
        return

    pending = get_pending_watchlist()
    if not pending:
        return

    print(f'[TRADE_WATCHER] checking {len(pending)} pending item(s)', flush=True)

    client = _restore_client()
    if not client:
        print('[TRADE_WATCHER] No saved session — skipping')
        return

    # Load index config map
    try:
        _idx_file = os.path.join(os.path.dirname(__file__), '..', 'indices.json')
        with open(_idx_file) as f:
            idx_map = {i['id']: i for i in json.load(f)}
    except Exception:
        idx_map = {
            'SENSEX':    {'feed_exch': 'B', 'feed_scrip': 999901},
            'NIFTY':     {'feed_exch': 'N', 'feed_scrip': 999920},
            'BANKNIFTY': {'feed_exch': 'N', 'feed_scrip': 999921},
            'FINNIFTY':  {'feed_exch': 'N', 'feed_scrip': 999922},
        }

    for item in pending:
        index_id = item['index_id']
        try:
            cfg = idx_map.get(index_id)
            if not cfg:
                print(f'[TRADE_WATCHER] unknown index {index_id}')
                continue

            # Get current LTP
            ltp_data = get_index_ltp(client, cfg['feed_exch'], cfg['feed_scrip'], index_id)
            ltp = ltp_data.get('ltp', 0)
            if ltp == 0:
                continue

            trigger_price = float(item['trigger_price'])
            condition     = (item['trigger_condition'] or 'above').lower()
            triggered     = (condition == 'above' and ltp >= trigger_price) or \
                            (condition == 'below' and ltp <= trigger_price)

            print(f'[TRADE_WATCHER] {index_id} LTP={ltp} | cond={condition} {trigger_price} | triggered={triggered}')

            if not triggered:
                continue

            # ── Condition met — place limit order ────────────────────────────
            scrip_code = int(item['scrip_code'] or 0)
            if not scrip_code:
                update_watchlist_failed(item['id'], 'No scrip_code — cannot place order')
                send_message(f'⚠️ <b>Watchlist {index_id}</b>: trigger hit but scrip_code missing')
                continue

            exch = 'B' if index_id == 'SENSEX' else 'N'

            # ── Fetch LIVE option price at trigger moment ─────────────────────
            live = get_ltp(client, scrip_code, exch, 'D')
            live_price = float(live.get('ltp', 0))
            stored_premium = float(item['premium'] or 0)
            # Use live price; fall back to stored premium if live fetch fails
            premium = live_price if live_price > 0 else stored_premium
            price   = _t(premium * 1.02) if premium > 0 else 0   # limit 2% above, tick-aligned

            print(f'[TRADE_WATCHER] {index_id} option LTP={live_price} stored={stored_premium} order_price={price}')

            actual_qty = _lot_qty(index_id, item['qty'] or 1)
            result = client.place_order(
                OrderType='B', Exchange=exch, ExchangeType='D',
                ScripCode=scrip_code, Qty=actual_qty,
                Price=price, IsIntraday=True, StopLossPrice=0, IsIOCOrder=False,
            )
            print(f'[TRADE_WATCHER] order result: {result!r}')

            if isinstance(result, dict):
                status_val = result.get('Status', -1)
                order_id   = (result.get('BrokerOrderId') or
                              result.get('RemoteOrderID') or
                              result.get('OrderId') or '')
            else:
                status_val, order_id = -1, ''

            try:
                status_int = int(status_val)
            except Exception:
                status_int = -1

            now_s = datetime.now(_IST).strftime('%H:%M')
            if status_int == 0 and order_id:
                update_watchlist_executed(item['id'], premium, str(order_id))
                # Place SL order immediately after buy confirmation
                sl_result, sl_trigger = _place_sl_order(
                    client, index_id, scrip_code, exch, premium, actual_qty)
                sl_note = f'\n🛡️ SL Order @ ₹{sl_trigger:.1f}' if sl_result else '\n⚠️ SL order failed'
                send_message(
                    f'✅ <b>Auto-Trade Executed — {index_id}</b>\n\n'
                    f'BUY {item["strike"]} {item["option_type"]} @ ₹{premium:.2f} (live)\n'
                    f'Order ID: {order_id}\n'
                    f'Triggered: LTP {ltp:,.0f} ({condition} {trigger_price:,.0f}) @ {now_s}'
                    f'{sl_note}'
                )
                print(f'[TRADE_WATCHER] ✅ {index_id} order placed: {order_id}')
            else:
                err_msg = (result.get('Message') or str(result))[:200] if isinstance(result, dict) else str(result)[:200]
                update_watchlist_failed(item['id'], err_msg)
                send_message(
                    f'❌ <b>Auto-Trade FAILED — {index_id}</b>\n'
                    f'{item["strike"]} {item["option_type"]} | {err_msg[:100]}'
                )
                print(f'[TRADE_WATCHER] ❌ order failed: {err_msg}')

        except Exception as e:
            print(f'[TRADE_WATCHER] Error processing item {item["id"]}: {e}')
            try:
                update_watchlist_failed(item['id'], str(e)[:200])
            except Exception:
                pass

    # ── Monitor active positions for SL / target exit ─────────────────────────
    try:
        active = [w for w in get_watchlist(status='executed')
                  if w.get('exit_price') is None and w.get('exit_at') is None
                  and int(w.get('scrip_code') or 0) > 0]
        if not active:
            return

        print(f'[TRADE_WATCHER] monitoring {len(active)} active position(s)')

        for pos in active:
            try:
                scrip_code = int(pos['scrip_code'])
                exch       = 'B' if pos['index_id'] == 'SENSEX' else 'N'
                ltp_data   = get_ltp(client, scrip_code, exch, 'D')
                cur_ltp    = float(ltp_data.get('ltp', 0))
                if cur_ltp == 0:
                    continue

                entry     = float(pos['execution_price'] or pos['premium'])
                sl_offset = float(pos.get('sl_offset') or 150)
                sl_price  = max(entry - sl_offset, 0.5)
                target_pr = entry + (3 * sl_offset)          # 1:3 R:R based on sl_offset
                qty       = _lot_qty(pos['index_id'], pos.get('qty') or 1)
                now_s     = datetime.now(_IST).strftime('%H:%M')

                if cur_ltp <= sl_price:
                    reason = 'sl_hit'
                elif cur_ltp >= target_pr:
                    reason = 'target_hit'
                else:
                    pnl = (cur_ltp - entry) * qty
                    print(f'[TRADE_WATCHER] {pos["index_id"]} {pos["strike"]}{pos["option_type"]} '
                          f'entry={entry} cur={cur_ltp} SL={sl_price:.1f} Tgt={target_pr:.1f} '
                          f'P&L={pnl:+.0f}')
                    continue

                # Place sell order to exit
                price  = _t(cur_ltp * 0.98)   # sell limit 2% below LTP, tick-aligned
                result = client.place_order(
                    OrderType='S', Exchange=exch, ExchangeType='D',
                    ScripCode=scrip_code, Qty=qty,
                    Price=price, IsIntraday=True, StopLossPrice=0, IsIOCOrder=False,
                )
                print(f'[TRADE_WATCHER] exit order: {result!r}')

                exit_order_id = ''
                if isinstance(result, dict):
                    st = int(result.get('Status', -1) or -1)
                    exit_order_id = str(result.get('BrokerOrderId') or result.get('RemoteOrderID') or '')
                    if st != 0:
                        print(f'[TRADE_WATCHER] ⚠️ exit order may have failed: {result}')

                update_watchlist_exit(pos['id'], cur_ltp, reason)
                emoji  = '🛑' if reason == 'sl_hit' else '🎯'
                pnl    = (cur_ltp - entry) * qty
                send_message(
                    f'{emoji} <b>{"SL Hit" if reason == "sl_hit" else "Target Hit"} — {pos["index_id"]}</b>\n\n'
                    f'{pos["strike"]} {pos["option_type"]} · Exit @ ₹{cur_ltp:.2f}\n'
                    f'Entry ₹{entry:.2f} | {"SL" if reason == "sl_hit" else "Target"} triggered @ {now_s}\n'
                    f'P&L: ₹{pnl:+.0f} ({qty} lot{"s" if qty > 1 else ""})'
                    + (f'\nOrder: {exit_order_id}' if exit_order_id else '')
                )
                print(f'[TRADE_WATCHER] {emoji} {reason} for {pos["index_id"]} {pos["strike"]}{pos["option_type"]}')

            except Exception as ae:
                print(f'[TRADE_WATCHER] active pos error id={pos["id"]}: {ae}')
    except Exception as me:
        print(f'[TRADE_WATCHER] active monitor error: {me}')

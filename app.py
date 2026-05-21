from flask import Flask, request, session, redirect, jsonify, render_template
import os
import json
import anthropic as _anthropic
from dotenv import load_dotenv
from modules.auth import process_callback, authenticated_clients, cred, try_restore_session
from modules.holdings import get_holdings_data
from modules.master import search_scrips, refresh_master, get_scrip_info, browse_scrips, get_status
from modules.market import (get_ltp, get_expiry_dates, get_option_chain_data,
                            get_sensex_ltp, get_index_ltp, get_historical_data,
                            get_today_ohlc, get_chart_data, get_components_ltp)
from modules.db import (init_db, save_sr, get_sr_history, delete_sr, get_snapshots,
                        save_chain_analysis, get_chain_analysis_history, delete_chain_analysis,
                        get_setting, set_setting,
                        save_market_summary, get_latest_market_summary, get_market_summary_history,
                        delete_market_summary, get_today_market_summary,
                        save_watchlist, get_watchlist, cancel_watchlist,
                        update_watchlist_item, update_watchlist_executed, update_watchlist_failed)

# ── Load index config from indices.json ────────────────────────────────────────
_INDICES_FILE = os.path.join(os.path.dirname(__file__), 'indices.json')

def _load_indices():
    try:
        with open(_INDICES_FILE) as f:
            return json.load(f)
    except Exception:
        return [{"id":"SENSEX","label":"SENSEX","feed_exch":"B","feed_scrip":999901,"opt_exch":"B","opt_symbol":"SENSEX"}]

INDICES = _load_indices()
INDEX_MAP = {i['id']: i for i in INDICES}

# ── Load components config ──────────────────────────────────────────────────────
_COMP_FILE = os.path.join(os.path.dirname(__file__), 'components.json')

def _load_components():
    try:
        with open(_COMP_FILE) as f:
            return json.load(f)
    except Exception:
        return {}

COMPONENTS = _load_components()

# ── Init SQLite DB ──────────────────────────────────────────────────────────────
try:
    init_db()
except Exception as _e:
    print(f'[DB] init failed: {_e}')

# ── Background scheduler ────────────────────────────────────────────────────────
try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from modules.scheduler import run_sensex_snapshot
    _scheduler = BackgroundScheduler(timezone='Asia/Kolkata')
    _scheduler.add_job(run_sensex_snapshot, 'interval', minutes=1, id='sensex_snapshot',
                       max_instances=1, misfire_grace_time=30)
    # Market Update job
    from modules.scheduler import run_market_update
    _mu_freq = int(get_setting('market_update_freq_min', '5'))
    if get_setting('market_update_enabled', 'false') == 'true':
        _scheduler.add_job(run_market_update, 'interval', minutes=_mu_freq,
                           id='market_update', max_instances=1, misfire_grace_time=60)
        print(f'[SCHEDULER] Market Update started — every {_mu_freq} min')
    # Trade Watchlist watcher — checks pending conditions every 2 min during market hours
    from modules.scheduler import run_trade_watcher
    _scheduler.add_job(run_trade_watcher, 'interval', minutes=2,
                       id='trade_watcher', max_instances=1, misfire_grace_time=60)
    print('[SCHEDULER] Trade Watcher started — every 2 min')
    _scheduler.start()
    print('[SCHEDULER] Started — SENSEX snapshots every 1 min during market hours')
except Exception as _e:
    print(f'[SCHEDULER] Failed to start: {_e}')

load_dotenv()

# ── In-memory log buffer ────────────────────────────────────────────────────────
import logging
import collections
import sys

class _MemHandler(logging.Handler):
    """Keep the last MAX_LINES log records in a deque."""
    MAX_LINES = 500
    def __init__(self):
        super().__init__()
        self.buf = collections.deque(maxlen=self.MAX_LINES)
    def emit(self, record):
        self.buf.append(self.format(record))

_mem_handler = _MemHandler()
_mem_handler.setFormatter(logging.Formatter('%(asctime)s  %(levelname)-7s  %(message)s',
                                             datefmt='%H:%M:%S'))

# Also redirect print() → logging so scheduler prints appear in the log
class _PrintCapture:
    def __init__(self, orig, level=logging.INFO):
        self._orig = orig
        self._level = level
        self._logger = logging.getLogger('app.print')
    def write(self, msg):
        msg = msg.rstrip('\n')
        if msg:
            self._logger.log(self._level, msg)
        self._orig.write(msg + '\n')
    def flush(self):
        self._orig.flush()
    def isatty(self):
        return False

_root_logger = logging.getLogger()
_root_logger.setLevel(logging.DEBUG)
_root_logger.addHandler(_mem_handler)
# Capture werkzeug (Flask request logs) too
logging.getLogger('werkzeug').setLevel(logging.INFO)
sys.stdout = _PrintCapture(sys.stdout, logging.INFO)

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "5paisa-flask-secret")
app.config['PERMANENT_SESSION_LIFETIME'] = __import__('datetime').timedelta(days=30)

PIN = os.getenv("APP_PIN", "7592")
DROPLET_IP = os.getenv("DROPLET_IP", "142.93.222.101")


def require_auth():
    # Only check the active browser session — no auto-restore.
    # Auto-restore happens only in verify_pin() so the PIN always gates access.
    cid = session.get('client_id')
    if cid:
        client = authenticated_clients.get(cid)
        if client:
            return client
    return None


# ── Auth routes ────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    if require_auth():
        return redirect('/dashboard')
    return render_template('pin.html', error=None)


@app.route('/verify-pin', methods=['POST'])
def verify_pin():
    if request.form.get('pin', '').strip() != PIN:
        return render_template('pin.html', error="Incorrect PIN. Please try again.")

    # Try to restore previous session — skip OAuth if still valid
    client_id = try_restore_session()
    if client_id:
        session.permanent = True
        session['authenticated'] = True
        session['client_id'] = client_id
        return redirect('/dashboard')

    # No valid saved session — go through OAuth
    session['pin_verified'] = True
    login_url = (
        f"https://dev-openapi.5paisa.com/WebVendorLogin/VLogin/Index"
        f"?VendorKey={cred['USER_KEY']}"
        f"&ResponseURL=http://{DROPLET_IP}:3000/callback"
    )
    return render_template('login.html', login_url=login_url)


@app.route('/callback')
def callback():
    result = process_callback(request.args)
    if result['success']:
        session.permanent = True
        session['authenticated'] = True
        session['client_id'] = result['client_id']
        session.pop('pin_verified', None)
        return redirect('/dashboard')
    return render_template('pin.html', error=result['error'])


@app.route('/logout')
def logout():
    # Lock only — clear the browser session but keep the server-side client
    # and the JWT file on disk so the next PIN entry restores instantly.
    session.clear()
    return redirect('/')


@app.route('/relogin')
def relogin():
    """Force fresh 5paisa OAuth — deletes saved JWT and goes to OAuth flow."""
    import os as _os
    session.clear()
    # Delete saved JWT so verify-pin won't restore the stale session
    _jwt_file = _os.path.join(_os.path.dirname(__file__), '.5paisa_session.json')
    try:
        _os.remove(_jwt_file)
    except Exception:
        pass
    login_url = (
        f"https://dev-openapi.5paisa.com/WebVendorLogin/VLogin/Index"
        f"?VendorKey={cred['USER_KEY']}"
        f"&ResponseURL=http://{DROPLET_IP}:3000/callback"
    )
    return render_template('login.html', login_url=login_url)


# ── Pages ──────────────────────────────────────────────────────────────────────

@app.route('/dashboard')
def dashboard():
    if not require_auth():
        return redirect('/')
    return render_template('dashboard.html')


@app.route('/sql')
def sql_browser():
    if not require_auth():
        return redirect('/')
    return render_template('sql.html')


@app.route('/architecture')
def architecture():
    if not require_auth():
        return redirect('/')
    return render_template('architecture.html')


# ── API ────────────────────────────────────────────────────────────────────────

@app.route('/api/holdings')
def api_holdings():
    client = require_auth()
    if not client:
        return jsonify({"error": "Not authenticated"}), 401
    return jsonify(get_holdings_data(client))


@app.route('/api/search')
def api_search():
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return jsonify({"results": []})
    return jsonify({"results": search_scrips(q)})


@app.route('/api/ltp')
def api_ltp():
    client = require_auth()
    if not client:
        return jsonify({"error": "Not authenticated"}), 401
    return jsonify(get_ltp(
        client,
        request.args.get('scripcode'),
        request.args.get('exch', 'N'),
        request.args.get('exch_type', 'C')
    ))


@app.route('/api/expiry')
def api_expiry():
    client = require_auth()
    if not client:
        return jsonify({"error": "Not authenticated"}), 401
    idx = request.args.get('index', '').upper()
    if idx and idx in INDEX_MAP:
        cfg = INDEX_MAP[idx]
        return jsonify(get_expiry_dates(client, cfg['opt_exch'], cfg['opt_symbol']))
    return jsonify(get_expiry_dates(
        client,
        request.args.get('exch', 'N'),
        request.args.get('symbol', '')
    ))


@app.route('/api/indices')
def api_indices():
    return jsonify(INDICES)


@app.route('/api/sensex-ltp')
def api_sensex_ltp():
    client = require_auth()
    if not client:
        return jsonify({"error": "Not authenticated"}), 401
    return jsonify(get_sensex_ltp(client))


@app.route('/api/index-ltp')
def api_index_ltp():
    client = require_auth()
    if not client:
        return jsonify({"error": "Not authenticated"}), 401
    idx = request.args.get('index', 'SENSEX').upper()
    if idx not in INDEX_MAP:
        return jsonify({"error": f"Unknown index: {idx}"}), 400
    cfg = INDEX_MAP[idx]
    return jsonify(get_index_ltp(
        client, cfg['feed_exch'], cfg['feed_scrip'], cfg.get('opt_symbol'),
        chart_scrip=cfg.get('chart_scrip', cfg['feed_scrip'])
    ))


@app.route('/api/option-chain')
def api_option_chain():
    client = require_auth()
    if not client:
        return jsonify({"error": "Not authenticated"}), 401
    idx = request.args.get('index', '').upper()
    if idx and idx in INDEX_MAP:
        cfg = INDEX_MAP[idx]
        return jsonify(get_option_chain_data(client, cfg['opt_exch'], cfg['opt_symbol'], request.args.get('expiry_ts', 0)))
    return jsonify(get_option_chain_data(
        client,
        request.args.get('exch', 'N'),
        request.args.get('symbol', ''),
        request.args.get('expiry_ts', 0)
    ))


@app.route('/api/debug-index')
def api_debug_index():
    """Find correct NIFTY/BANKNIFTY scrip codes from master data."""
    # Try authenticated client first, fall back to fresh restore
    client = require_auth()
    if not client:
        from modules.auth import try_restore_session, authenticated_clients
        cid = try_restore_session()
        client = authenticated_clients.get(cid) if cid else None
    if not client:
        return jsonify({"error": "Not authenticated — log in first"}), 401

    results = {}

    # 1. Search master scrip data for NIFTY/BANKNIFTY
    try:
        from modules.master import search_scrips
        for q in ['NIFTY', 'BANKNIFTY', 'BANK NIFTY']:
            hits = search_scrips(q)
            results[f"master_{q}"] = hits[:20]  # top 20 matches
    except Exception as e:
        results["master_error"] = str(e)

    # 2. Try market feed with wider scrip code range
    from datetime import date, timedelta
    today     = date.today().strftime('%Y-%m-%d')
    from_date = (date.today() - timedelta(days=30)).strftime('%Y-%m-%d')

    for exch, et, sc, label in [
        ('N','C',999920,'NIFTY-C-999920'), ('N','D',999920,'NIFTY-D-999920'),
        ('N','C',26000, 'NIFTY-C-26000'),  ('N','D',26000, 'NIFTY-D-26000'),
        ('N','C',50,    'NIFTY-C-50'),     ('N','D',50,    'NIFTY-D-50'),
        ('N','C',999921,'BNFTY-C-999921'), ('N','D',999921,'BNFTY-D-999921'),
        ('N','C',26009, 'BNFTY-C-26009'),  ('N','D',26009, 'BNFTY-D-26009'),
    ]:
        try:
            df = client.historical_data(exch, et, sc, '1d', from_date, today)
            if df is not None and len(df) > 0:
                results[f"hist_{label}"] = f"WORKS rows={len(df)} last_close={df.iloc[-1].get('Close','?')}"
            else:
                results[f"hist_{label}"] = "empty"
        except Exception as e:
            results[f"hist_{label}"] = f"ERR:{str(e)[:80]}"

    return jsonify(results)


@app.route('/api/debug-ohlc')
def api_debug_ohlc():
    """Debug: show raw historical_data columns and values for OHLC troubleshooting."""
    client = require_auth()
    if not client:
        return jsonify({'error': 'Not authenticated'}), 401
    idx = request.args.get('index', 'SENSEX').upper()
    cfg = INDEX_MAP.get(idx, INDEX_MAP.get('SENSEX'))
    exch   = cfg.get('chart_exch', cfg['feed_exch'])
    scrip  = int(cfg.get('chart_scrip', cfg['feed_scrip']))
    from datetime import date as _d, timedelta as _td
    today     = _d.today().strftime('%Y-%m-%d')
    past_week = (_d.today() - _td(days=10)).strftime('%Y-%m-%d')
    results = {'index': idx, 'exch': exch, 'scrip': scrip}
    for et in ('C', 'D'):
        for interval, frm, to in [('15m', today, today), ('1d', past_week, today)]:
            key = f'{et}_{interval}'
            try:
                df = client.historical_data(exch, et, scrip, interval, frm, to)
                if df is None or len(df) == 0:
                    results[key] = 'empty'
                else:
                    last = df.iloc[-1]
                    results[key] = {
                        'rows':    len(df),
                        'columns': list(df.columns),
                        'last':    {k: str(v) for k, v in last.items()},
                    }
            except Exception as e:
                results[key] = f'ERR: {str(e)[:120]}'
    return jsonify(results)


@app.route('/api/history')
def api_history():
    client = require_auth()
    if not client:
        return jsonify({"error": "Not authenticated"}), 401
    return jsonify(get_historical_data(
        client,
        request.args.get('exch', 'B'),
        request.args.get('exch_type', 'D'),
        request.args.get('scripcode', 0),
        request.args.get('interval', '15m'),
        request.args.get('days', 2)
    ))


@app.route('/api/browse')
def api_browse():
    return jsonify(browse_scrips(
        cat=request.args.get('cat', 'all'),
        query=request.args.get('q', ''),
        page=int(request.args.get('page', 1)),
        limit=50
    ))


@app.route('/api/master/status')
def api_master_status():
    return jsonify(get_status())


@app.route('/api/master/refresh')
def api_master_refresh():
    try:
        df = refresh_master()
        return jsonify({"success": True, "rows": len(df)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/analyze-chain')
def api_analyze_chain():
    client = require_auth()
    if not client:
        return jsonify({"error": "Not authenticated"}), 401

    idx        = request.args.get('index', 'SENSEX').upper()
    expiry_ts  = request.args.get('expiry_ts', 0)
    ltp        = float(request.args.get('ltp', 0))
    prev_close = float(request.args.get('prev_close', 0))
    expiry_lbl = request.args.get('expiry_label', '')

    cfg = INDEX_MAP.get(idx)
    if not cfg:
        return jsonify({"error": f"Unknown index: {idx}"}), 400

    chain = get_option_chain_data(client, cfg['opt_exch'], cfg['opt_symbol'], expiry_ts)
    if 'error' in chain:
        return jsonify(chain)

    rows = chain.get('option_chain', [])
    if not rows:
        return jsonify({"error": "No option chain data"})

    # ── Stats ─────────────────────────────────────────────────────────────────
    total_ce_oi = sum(r['ce_oi'] for r in rows)
    total_pe_oi = sum(r['pe_oi'] for r in rows)
    pcr         = round(total_pe_oi / total_ce_oi, 2) if total_ce_oi > 0 else 0

    # Max pain — strike with min total option pain across all strikes
    pain_rows = []
    for strike_row in rows:
        pain = sum(
            max(0, (strike_row['strike'] - r['strike'])) * r['ce_oi'] +
            max(0, (r['strike'] - strike_row['strike'])) * r['pe_oi']
            for r in rows
        )
        pain_rows.append((pain, strike_row['strike']))
    max_pain = min(pain_rows, key=lambda x: x[0])[1] if pain_rows else 0

    # Highest CE & PE OI strikes
    top_ce = sorted(rows, key=lambda r: r['ce_oi'], reverse=True)[:5]
    top_pe = sorted(rows, key=lambda r: r['pe_oi'], reverse=True)[:5]

    # 20 strikes nearest to LTP for detailed analysis
    near_rows = sorted(rows, key=lambda r: abs(r['strike'] - ltp))[:20]
    chain_txt = "Strike | CE_LTP | CE_OI | CE_ChgOI | CE_Vol | PE_LTP | PE_OI | PE_ChgOI | PE_Vol\n"
    for r in near_rows:
        chain_txt += (f"{int(r['strike'])} | {r['ce_ltp']} | {r['ce_oi']} | {r['ce_chg_oi']} | "
                      f"{r['ce_vol']} | {r['pe_ltp']} | {r['pe_oi']} | {r['pe_chg_oi']} | {r['pe_vol']}\n")

    chg_pct = round((ltp - prev_close) / prev_close * 100, 2) if prev_close > 0 else 0
    chg_abs = round(ltp - prev_close, 2)

    # ── Fresh S/R analysis (inline, before main Claude call) ─────────────────
    sr_text = 'No saved S/R analysis available for this index.'
    sr_meta = None
    try:
        c_exch  = cfg.get('chart_exch',  cfg['feed_exch'])
        c_scrip = cfg.get('chart_scrip', cfg['feed_scrip'])
        chart_sr = get_chart_data(client, c_exch, c_scrip, interval='1d', days=380)
        if chart_sr.get('candles'):
            candles_sr = chart_sr['candles']
            ltp_sr     = candles_sr[-1]['close'] if candles_sr else ltp
            recent_sr  = candles_sr[-60:]
            from datetime import datetime as _dt_sr
            ohlc_sr = 'Date | O | H | L | C\n'
            for _c in recent_sr:
                try:
                    _d = _dt_sr.utcfromtimestamp(_c['time']).strftime('%d-%b-%y')
                except Exception:
                    _d = str(_c['time'])
                ohlc_sr += f"{_d} | {_c['open']:.0f} | {_c['high']:.0f} | {_c['low']:.0f} | {_c['close']:.0f}\n"
            yr_hi = max(c['high'] for c in candles_sr if c['high'] > 0)
            yr_lo = min(c['low']  for c in candles_sr if c['low']  > 0)
            one_pct_sr = round(ltp_sr * 0.01)
            sr_prompt = f"""You are a price action trader specialising in index options on Indian markets.
Index: {idx}  |  Current Price: {ltp_sr:.0f}
52-Week High: {yr_hi:.0f}  |  52-Week Low: {yr_lo:.0f}
1% range: {ltp_sr - one_pct_sr:.0f} – {ltp_sr + one_pct_sr:.0f}
Daily OHLC — last 60 trading days:
{ohlc_sr}
Find exactly 2 SUPPORT levels and 2 RESISTANCE levels within 1% of current price.
A level must have caused a SHARP bounce/rejection (1%+ move in 1 day) at least twice.
Respond ONLY in valid JSON (no markdown):
{{"supports":[{{"level":0,"reason":""}}],"resistances":[{{"level":0,"reason":""}}],"verdict":""}}
Return exactly 2 supports and 2 resistances."""
            ac_sr = _anthropic.Anthropic()
            rsp_sr = ac_sr.messages.create(
                model='claude-haiku-4-5', max_tokens=600,
                messages=[{'role': 'user', 'content': sr_prompt}]
            )
            raw_sr = rsp_sr.content[0].text.strip()
            if raw_sr.startswith('```'):
                raw_sr = raw_sr.split('```')[1]
                if raw_sr.startswith('json'): raw_sr = raw_sr[4:]
            sr_data = json.loads(raw_sr.strip())
            fresh_sups = sr_data.get('supports', [])
            fresh_ress = sr_data.get('resistances', [])
            # Save fresh S/R to DB
            try:
                save_sr(
                    index_id=idx, ltp=ltp_sr,
                    supports=fresh_sups, resistances=fresh_ress,
                    valid_today=[], verdict=sr_data.get('verdict', ''),
                )
            except Exception as _srs:
                print(f'[SR] save error: {_srs}')
            sup_str = ', '.join(str(s['level']) for s in fresh_sups)
            res_str = ', '.join(str(r['level']) for r in fresh_ress)
            sr_text = (f"Supports: {sup_str or '—'}\n"
                       f"Resistances: {res_str or '—'}\n"
                       f"S/R Verdict: {sr_data.get('verdict','')}")
            sr_meta = {
                'saved_at':    'fresh',
                'ltp':         ltp_sr,
                'supports':    [s['level'] for s in fresh_sups],
                'resistances': [r['level'] for r in fresh_ress],
            }
            print(f'[MS] {idx} fresh S/R: sup={sup_str} res={res_str}')
        else:
            # Fall back to saved S/R from DB
            sr_history = get_sr_history(idx, limit=1)
            if sr_history:
                sr     = sr_history[0]
                sups   = (sr.get('supports')    or [])[:5]
                ress   = (sr.get('resistances') or [])[:5]
                sup_str = ', '.join(str(s['level']) for s in sups)
                res_str = ', '.join(str(r['level']) for r in ress)
                sr_text = (f"Supports: {sup_str or '—'}\n"
                           f"Resistances: {res_str or '—'}\n"
                           f"(S/R from DB at LTP {sr['ltp']} on {sr['saved_at']})")
                sr_meta = {
                    'saved_at':    sr['saved_at'],
                    'ltp':         sr['ltp'],
                    'supports':    [s['level'] for s in sups],
                    'resistances': [r['level'] for r in ress],
                }
    except Exception as _sre:
        print(f'[SR] fresh analysis error: {_sre}')
        # Fall back to saved S/R
        try:
            sr_history = get_sr_history(idx, limit=1)
            if sr_history:
                sr     = sr_history[0]
                sups   = (sr.get('supports')    or [])[:5]
                ress   = (sr.get('resistances') or [])[:5]
                sup_str = ', '.join(str(s['level']) for s in sups)
                res_str = ', '.join(str(r['level']) for r in ress)
                sr_text = (f"Supports: {sup_str or '—'}\n"
                           f"Resistances: {res_str or '—'}\n"
                           f"(S/R from DB, error fetching fresh: {str(_sre)[:60]})")
                sr_meta = {
                    'saved_at':    sr['saved_at'],
                    'ltp':         sr['ltp'],
                    'supports':    [s['level'] for s in sups],
                    'resistances': [r['level'] for r in ress],
                }
        except Exception:
            pass

    # ── Previous market summaries history (last 5) for context ────────────────
    prev_context = ''
    prev_meta    = None
    try:
        history = get_market_summary_history(idx, limit=5)
        if history:
            lines = ['\n═══ PREVIOUS MARKET SUMMARY HISTORY (newest first) ═══']
            for i, prev in enumerate(history):
                prev_dir = '—'; prev_trade = '—'
                if prev.get('structured'):
                    try:
                        ps = json.loads(prev['structured'])
                        prev_dir   = ps.get('direction', '—').upper()
                        pt         = ps.get('trade', {})
                        prev_trade = f"{pt.get('strike')} {pt.get('type')} @ ₹{pt.get('premium')}"
                    except Exception:
                        pass
                lines.append(
                    f"\n[{i+1}] {prev['date']} {prev['time']} | LTP {prev['ltp']} | {prev_dir} | Trade: {prev_trade}"
                )
                lines.append(prev['analysis'][:400] + ('…' if len(prev['analysis']) > 400 else ''))
            lines.append('\n[Compare history — note bias shifts, changing OI walls, evolving levels]\n')
            prev_context = '\n'.join(lines)
            # Meta uses the most recent for display
            first = history[0]
            try:
                ps0      = json.loads(first.get('structured') or '{}')
                dir0     = ps0.get('direction', '—').upper()
                pt0      = ps0.get('trade', {})
                trade0   = f"{pt0.get('strike')} {pt0.get('type')} @ ₹{pt0.get('premium')}"
            except Exception:
                dir0, trade0 = '—', '—'
            prev_meta = {
                'date':      first['date'],
                'time':      first['time'],
                'ltp':       first['ltp'],
                'direction': dir0,
                'trade':     trade0,
            }
            print(f'[MS] {idx} history: {len(history)} prev summaries loaded')
        else:
            print(f'[MS] {idx} — no previous summary found')
    except Exception as _e:
        print(f'[MS] prev fetch error: {_e}')

    prompt = f"""You are an expert Indian options trader. Analyze {idx} and respond ONLY in valid JSON — no text outside the JSON.

INPUT DATA
Index: {idx} | LTP: {ltp} | Prev Close: {prev_close} | Change: {chg_abs:+.2f} ({chg_pct:+.2f}%)
Expiry: {expiry_lbl} | PCR: {pcr} | Max Pain: {int(max_pain)}
Top CE OI walls: {', '.join(f"{int(r['strike'])}(OI:{r['ce_oi']},LTP:₹{r['ce_ltp']})" for r in top_ce)}
Top PE OI walls: {', '.join(f"{int(r['strike'])}(OI:{r['pe_oi']},LTP:₹{r['pe_ltp']})" for r in top_pe)}

S/R LEVELS (Technical):
{sr_text}

OPTION CHAIN (20 strikes near LTP):
{chain_txt}
{prev_context}
Respond ONLY with this JSON (no markdown, no text outside JSON):
{{
  "direction": "bullish|bearish|neutral",
  "context": "2-3 sentences: what data (PCR, max pain gap, OI walls, S/R, prev bias) drove the conclusion",
  "signals": [
    "signal 1 — one line, specific level/number",
    "signal 2",
    "signal 3",
    "signal 4",
    "signal 5"
  ],
  "trade": {{
    "action": "BUY",
    "strike": 0,
    "type": "CE or PE",
    "premium": 0.0,
    "trigger_price": 0,
    "trigger_condition": "above",
    "entry_trigger": "one line: what to watch at the trigger_price level",
    "entry_timing": "best time window, e.g. '9:20-9:45 AM after opening range forms'",
    "sl": 0.0,
    "target": 0.0,
    "reason": "one sentence why this strike"
  }}
}}

TRADE RULES:
- Pick ONE trade only (CE if bullish, PE if bearish)
- trigger_price: EXACT integer index price to watch (e.g. 24050)
- trigger_condition: "above" = enter when {idx} >= trigger_price (use for CE); "below" = enter when {idx} <= trigger_price (use for PE)
- entry_trigger: brief human-readable summary of the trigger
- entry_timing: time of day guidance
- sl = premium x 0.70 (30% loss = stop)
- target = premium + 3 x (premium - sl)  exactly 1:3 R:R
- Round sl and target to nearest 0.5
- Choose strike near ATM with strong OI backing"""

    try:
        ac = _anthropic.Anthropic()
        resp = ac.messages.create(
            model="claude-haiku-4-5",
            max_tokens=900,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = resp.content[0].text.strip()

        # Strip markdown code fences if present
        if raw.startswith('```'):
            raw = raw.split('```')[1]
            if raw.startswith('json'): raw = raw[4:]
        raw = raw.strip()

        structured = json.loads(raw)

        # Build a plain-text version for DB storage
        t = structured.get('trade', {})
        analysis_text = (
            f"Direction: {structured.get('direction','').upper()}\n\n"
            f"Context: {structured.get('context','')}\n\n"
            f"Signals:\n" +
            '\n'.join(f"• {s}" for s in structured.get('signals', [])) +
            f"\n\nTrade: BUY {t.get('strike')} {t.get('type')} @ ₹{t.get('premium')} | "
            f"SL ₹{t.get('sl')} | Target ₹{t.get('target')} | 1:3 R:R\n"
            f"Trigger: {t.get('entry_trigger','')}\n"
            f"Timing: {t.get('entry_timing','')}\n"
            f"{t.get('reason','')}"
        )

        # Save to market_summary (with structured JSON for cache replay)
        try:
            save_market_summary(
                index_id=idx, expiry_label=expiry_lbl,
                ltp=ltp, pcr=pcr, max_pain=max_pain,
                analysis=analysis_text,
                structured=json.dumps(structured),
            )
        except Exception as _se:
            print(f'[DB] market summary save error: {_se}')

        # Legacy chain_analysis save
        try:
            save_chain_analysis(
                index_id=idx, expiry_label=expiry_lbl,
                expiry_ts=int(expiry_ts), ltp=ltp,
                pcr=pcr, max_pain=max_pain, analysis=analysis_text,
            )
        except Exception as _se:
            print(f'[DB] chain analysis save error: {_se}')

        # Auto-save to trade watchlist — replace any existing pending entry for this index
        watchlist_id = None
        try:
            t_save = structured.get('trade', {})
            t_strike     = int(t_save.get('strike', 0))
            t_type       = (t_save.get('type') or '').upper()        # CE / PE
            t_premium    = float(t_save.get('premium', 0))
            t_trigger    = float(t_save.get('trigger_price', 0))
            t_condition  = (t_save.get('trigger_condition') or 'above').lower()
            t_sl         = float(t_save.get('sl', 0))
            t_target     = float(t_save.get('target', 0))
            if t_strike and t_type and t_trigger:
                # Find scrip_code from option chain
                scrip_key  = 'ce_scrip' if t_type == 'CE' else 'pe_scrip'
                t_scrip    = 0
                for row_r in rows:
                    if int(row_r['strike']) == t_strike:
                        t_scrip = int(row_r.get(scrip_key, 0))
                        # Also use chain LTP if premium is 0
                        if t_premium == 0:
                            ltp_key = 'ce_ltp' if t_type == 'CE' else 'pe_ltp'
                            t_premium = float(row_r.get(ltp_key, 0))
                        break
                watchlist_id = save_watchlist(
                    index_id=idx, strike=t_strike, option_type=t_type,
                    scrip_code=t_scrip, premium=t_premium,
                    trigger_price=t_trigger, trigger_condition=t_condition,
                    sl=t_sl, target=t_target, qty=1, sl_offset=150,
                    notes=f"Auto from analysis @ {ltp}",
                )
                print(f'[WATCHLIST] {idx} saved id={watchlist_id} '
                      f'{t_strike}{t_type} trigger={t_condition} {t_trigger}')
        except Exception as _we:
            print(f'[WATCHLIST] save error: {_we}')

        return jsonify({
            "structured":   structured,
            "summary":      analysis_text,
            "pcr":          pcr,
            "max_pain":     max_pain,
            "total_ce_oi":  total_ce_oi,
            "total_pe_oi":  total_pe_oi,
            "change":       chg_abs,
            "change_pct":   chg_pct,
            "ltp":          ltp,
            "expiry_label": expiry_lbl,
            "sr_used":      sr_meta,           # None if no S/R saved
            "prev_used":    bool(prev_context), # True if previous analysis was included
            "prev_meta":    prev_meta,          # dict with date/time/ltp/direction/trade or None
            "watchlist_id": watchlist_id,       # id of the auto-saved watchlist entry or None
        })
    except json.JSONDecodeError as e:
        print(f'[MS] JSON parse error: {e} | raw: {raw[:200]}')
        # Fallback: return raw text
        return jsonify({
            "summary": raw, "pcr": pcr, "max_pain": max_pain,
            "total_ce_oi": total_ce_oi, "total_pe_oi": total_pe_oi,
            "change": chg_abs, "change_pct": chg_pct,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/market-news')
def api_market_news():
    """Fetch top 5 market news + global context quotes (GIFT Nifty, VIX, DXY, Crude)."""
    if not require_auth():
        return jsonify({'error': 'Not authenticated'}), 401
    try:
        from modules.market_context import get_market_context
        ctx = get_market_context()
        return jsonify({'quotes': ctx['quotes'], 'news': ctx['news']})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/market-summary/today')
def api_market_summary_today():
    """Return today's most recent market summary for an index (IST date), or found=False."""
    if not require_auth():
        return jsonify({'error': 'Not authenticated'}), 401
    idx = request.args.get('index', 'SENSEX').upper()
    row = get_today_market_summary(idx)
    if not row:
        return jsonify({'found': False})
    # Parse stored structured JSON so the frontend can render it identically
    structured = None
    if row.get('structured'):
        try:
            structured = json.loads(row['structured'])
        except Exception:
            pass
    return jsonify({
        'found':        True,
        'date':         row['date'],
        'time':         row['time'],
        'ltp':          row['ltp'],
        'pcr':          row['pcr'],
        'max_pain':     row['max_pain'],
        'analysis':     row['analysis'],
        'structured':   structured,
        'expiry_label': row.get('expiry_label', ''),
        'sr_used':      None,   # not stored per-summary; shown as N/A for cached
        'prev_used':    False,
        'prev_meta':    None,
    })


@app.route('/api/watchlist')
def api_watchlist_get():
    if not require_auth():
        return jsonify({'error': 'Not authenticated'}), 401
    idx    = request.args.get('index', '').upper() or None
    status = request.args.get('status', '')        or None
    limit  = int(request.args.get('limit', 20))
    return jsonify({'watchlist': get_watchlist(index_id=idx, status=status, limit=limit)})


@app.route('/api/watchlist/<int:wid>', methods=['DELETE'])
def api_watchlist_cancel(wid):
    if not require_auth():
        return jsonify({'error': 'Not authenticated'}), 401
    cancelled = cancel_watchlist(wid)
    return jsonify({'success': True, 'cancelled': cancelled})


@app.route('/api/watchlist/<int:wid>', methods=['PATCH'])
def api_watchlist_update(wid):
    """Update qty and sl_offset on a pending watchlist entry."""
    if not require_auth():
        return jsonify({'error': 'Not authenticated'}), 401
    body      = request.get_json() or {}
    qty       = int(body.get('qty', 1))
    sl_offset = float(body.get('sl_offset', 150))
    changed   = update_watchlist_item(wid, qty, sl_offset)
    return jsonify({'success': True, 'changed': changed})


@app.route('/api/watchlist/<int:wid>/execute', methods=['POST'])
def api_watchlist_execute(wid):
    """Manually execute a pending watchlist entry at current live option price."""
    client = require_auth()
    if not client:
        return jsonify({'error': 'Not authenticated'}), 401
    # Fetch the item
    items = [i for i in get_watchlist(status='pending') if i['id'] == wid]
    if not items:
        return jsonify({'error': 'Item not found or not pending'}), 404
    item       = items[0]
    index_id   = item['index_id']
    scrip_code = int(item['scrip_code'] or 0)
    if not scrip_code:
        return jsonify({'error': 'No scrip_code — cannot place order'}), 400
    exch = 'B' if index_id == 'SENSEX' else 'N'
    _LOT_SIZES = {'SENSEX': 20, 'NIFTY': 65, 'BANKNIFTY': 30, 'FINNIFTY': 30}
    actual_qty = int(item['qty'] or 1) * _LOT_SIZES.get(index_id, 1)
    # Fetch live option price
    live = get_ltp(client, scrip_code, exch, 'D')
    live_price     = float(live.get('ltp', 0))
    stored_premium = float(item['premium'] or 0)
    premium        = live_price if live_price > 0 else stored_premium
    price          = round(premium * 1.02, 2) if premium > 0 else 0
    try:
        result = client.place_order(
            OrderType='B', Exchange=exch, ExchangeType='D',
            ScripCode=scrip_code, Qty=actual_qty,
            Price=price, IsIntraday=True, StopLossPrice=0, IsIOCOrder=False,
        )
        if isinstance(result, dict):
            status_int = int(result.get('Status', -1) or -1)
            order_id   = str(result.get('BrokerOrderId') or result.get('RemoteOrderID') or result.get('OrderId') or '')
        else:
            status_int, order_id = -1, ''
        if status_int == 0 and order_id:
            update_watchlist_executed(wid, premium, order_id)
            # Place SL order immediately after buy confirmation
            from modules.scheduler import _place_sl_order
            sl_result, sl_trigger = _place_sl_order(
                client, index_id, scrip_code, exch, premium, actual_qty)
            from modules.telegram import send_message
            from datetime import datetime as _dt2, timezone as _tz2, timedelta as _td2
            now_s = _dt2.now(_tz2(_td2(hours=5, minutes=30))).strftime('%H:%M')
            sl_note = f'\n🛡️ SL Order @ ₹{sl_trigger:.1f}' if sl_result else '\n⚠️ SL order failed'
            send_message(
                f'✅ <b>Manual Trade Executed — {index_id}</b>\n\n'
                f'BUY {item["strike"]} {item["option_type"]} @ ₹{premium:.2f} (live)\n'
                f'Order ID: {order_id} @ {now_s}'
                f'{sl_note}'
            )
            return jsonify({'success': True, 'order_id': order_id, 'premium': premium,
                            'sl_trigger': sl_trigger})
        else:
            err = (result.get('Message') or str(result))[:200] if isinstance(result, dict) else str(result)[:200]
            update_watchlist_failed(wid, err)
            return jsonify({'error': err}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/market-summary/history')
def api_market_summary_history():
    client = require_auth()
    if not client:
        return jsonify({'error': 'Not authenticated'}), 401
    idx   = request.args.get('index', 'SENSEX').upper()
    limit = int(request.args.get('limit', 20))
    return jsonify({'history': get_market_summary_history(idx, limit)})


@app.route('/api/market-summary/history/<int:record_id>', methods=['DELETE'])
def api_delete_market_summary(record_id):
    client = require_auth()
    if not client:
        return jsonify({'error': 'Not authenticated'}), 401
    deleted = delete_market_summary(record_id)
    return jsonify({'success': True, 'deleted': deleted})


@app.route('/api/analyze')
def api_analyze():
    client = require_auth()
    if not client:
        return jsonify({"error": "Not authenticated"}), 401

    ce_scrip = request.args.get('ce_scrip', 0, type=int)
    pe_scrip = request.args.get('pe_scrip', 0, type=int)
    strike   = request.args.get('strike', '')
    interval = request.args.get('interval', '15m')
    days     = request.args.get('days', 2, type=int)

    def fmt_candles(data, label):
        if 'error' in data or not data.get('candles'):
            return f"{label}: No data available"
        cs = data['candles'][-40:]
        lines = [f"{label} ({len(cs)} candles, {interval} interval):"]
        for c in cs:
            lines.append(
                f"  {c.get('Datetime','')} "
                f"O:{float(c.get('Open',0)):.0f} "
                f"H:{float(c.get('High',0)):.0f} "
                f"L:{float(c.get('Low',0)):.0f} "
                f"C:{float(c.get('Close',0)):.0f} "
                f"V:{int(c.get('Volume',0))}"
            )
        return "\n".join(lines)

    ce_text = fmt_candles(
        get_historical_data(client, 'B', 'D', ce_scrip, interval, days),
        f"SENSEX {strike} CE"
    ) if ce_scrip else f"SENSEX {strike} CE: Not available"

    pe_text = fmt_candles(
        get_historical_data(client, 'B', 'D', pe_scrip, interval, days),
        f"SENSEX {strike} PE"
    ) if pe_scrip else f"SENSEX {strike} PE: Not available"

    prompt = f"""You are a professional options trader. Analyze this {interval} OHLCV data for SENSEX {strike} strike and give a trading summary.

{ce_text}

{pe_text}

Provide a concise analysis with exactly these sections:
1. **Trend** — CE and PE price direction (rising/falling/sideways)
2. **Key Levels** — notable support/resistance for each option
3. **Volume Signal** — any significant volume spikes or dryup
4. **Market Bias** — bullish / bearish / neutral with one-line reason
5. **Trade Idea** — specific entry if a clear setup exists, otherwise "No clear setup"

Max 250 words. Use ₹ for prices. Be direct and specific."""

    try:
        ac = _anthropic.Anthropic()
        resp = ac.messages.create(
            model="claude-haiku-4-5",
            max_tokens=700,
            messages=[{"role": "user", "content": prompt}]
        )
        return jsonify({"summary": resp.content[0].text})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/today-ohlc')
def api_today_ohlc():
    client = require_auth()
    if not client:
        return jsonify({'error': 'Not authenticated'}), 401
    idx = request.args.get('index', 'SENSEX').upper()
    if idx not in INDEX_MAP:
        return jsonify({'error': f'Unknown index: {idx}'}), 400
    cfg = INDEX_MAP[idx]
    # Must use chart_scrip (e.g. 999920000) not feed_scrip (999920) for historical data
    return jsonify(get_today_ohlc(
        client,
        cfg.get('chart_exch', cfg['feed_exch']),
        cfg.get('chart_scrip', cfg['feed_scrip'])
    ))


@app.route('/api/chart-data')
def api_chart_data():
    client = require_auth()
    if not client:
        return jsonify({'error': 'Not authenticated'}), 401
    idx      = request.args.get('index', 'SENSEX').upper()
    interval = request.args.get('interval', '4h')
    days     = int(request.args.get('days', 365))
    if idx not in INDEX_MAP:
        return jsonify({'error': f'Unknown index: {idx}'}), 400
    cfg = INDEX_MAP[idx]
    c_exch  = cfg.get('chart_exch',  cfg['feed_exch'])
    c_scrip = cfg.get('chart_scrip', cfg['feed_scrip'])
    result  = get_chart_data(client, c_exch, c_scrip, interval, days)
    if result.get('error') == 'session_expired':
        return jsonify({'error': 'session_expired'}), 401
    return jsonify(result)


@app.route('/api/aux-chart')
def api_aux_chart():
    """Fetch 1-month daily candles for GIFT Nifty or India VIX."""
    client = require_auth()
    if not client:
        return jsonify({'error': 'Not authenticated'}), 401
    key = request.args.get('key', '').upper()

    # Scrip definitions — (exch, exch_type, scrip_code)
    _AUX = {
        'INDIAVIX':  [('N', 'C', 999920027), ('N', 'D', 999920027)],
        'GIFTNIFTY': [('N', 'C', 999920028), ('N', 'D', 999920028),
                      ('N', 'C', 13),        ('N', 'D', 13)],
    }
    if key not in _AUX:
        return jsonify({'error': f'Unknown key: {key}'}), 400

    from datetime import date as _d, timedelta as _td, datetime as _dt2
    today     = _d.today().strftime('%Y-%m-%d')
    from_date = (_d.today() - _td(days=35)).strftime('%Y-%m-%d')

    for exch, et, scrip in _AUX[key]:
        try:
            df = client.historical_data(exch, et, int(scrip), '1d', from_date, today)
            if df is None or isinstance(df, str) or len(df) < 3:
                continue
            candles = []
            for _, row in df.iterrows():
                dt_val = row.get('Datetime') or row.get('datetime') or ''
                try:
                    s  = str(dt_val)[:10]
                    dt = _dt2.strptime(s, '%Y-%m-%d')
                    unix_ts = int((dt - _dt2(1970, 1, 1) - __import__('datetime').timedelta(hours=5, minutes=30)).total_seconds())
                except Exception:
                    continue
                from modules.market import _extract_ohlc_row
                o, h, l, c = _extract_ohlc_row(row)
                val = c if c > 0 else o
                if val > 0:
                    candles.append({'time': unix_ts, 'value': val})
            if len(candles) >= 3:
                return jsonify({'candles': candles, 'scrip': scrip, 'key': key})
        except Exception as e:
            err = str(e).lower()
            if '401' in err or 'unauthorized' in err:
                return jsonify({'error': 'session_expired'}), 401
            continue

    return jsonify({'error': f'No data available for {key}', 'candles': []})


@app.route('/api/analyze-sr')
def api_analyze_sr():
    client = require_auth()
    if not client:
        return jsonify({'error': 'Not authenticated'}), 401
    idx = request.args.get('index', 'SENSEX').upper()
    if idx not in INDEX_MAP:
        return jsonify({'error': f'Unknown index: {idx}'}), 400
    cfg = INDEX_MAP[idx]

    # Fetch 1-year daily candles for S/R analysis
    c_exch  = cfg.get('chart_exch',  cfg['feed_exch'])
    c_scrip = cfg.get('chart_scrip', cfg['feed_scrip'])
    chart = get_chart_data(client, c_exch, c_scrip, interval='1d', days=380)
    if 'error' in chart or not chart.get('candles'):
        return jsonify({'error': 'Could not fetch historical data for S/R analysis'})

    candles = chart['candles']
    ltp     = candles[-1]['close'] if candles else 0

    # Build last 60 days OHLC text
    recent  = candles[-60:]
    from datetime import datetime as _dt
    def fmt_ts(ts):
        try:    return _dt.utcfromtimestamp(ts).strftime('%d-%b-%y')
        except: return str(ts)

    ohlc_txt = 'Date | O | H | L | C\n'
    for c in recent:
        ohlc_txt += f"{fmt_ts(c['time'])} | {c['open']:.0f} | {c['high']:.0f} | {c['low']:.0f} | {c['close']:.0f}\n"

    yr_high = max(c['high']  for c in candles if c['high'] > 0)
    yr_low  = min(c['low']   for c in candles if c['low']  > 0)

    # Fetch global market context (GIFT Nifty, VIX, DXY, Crude + news)
    from modules.market_context import get_market_context
    try:
        ctx = get_market_context()
        ctx_txt = ctx['as_text']
    except Exception:
        ctx_txt = '(global context unavailable)'

    one_pct = round(ltp * 0.01)

    prompt = f"""You are a price action trader specialising in index options on Indian markets.

Index: {idx}  |  Current Price: {ltp:.0f}
52-Week High: {yr_high:.0f}  |  52-Week Low: {yr_low:.0f}
1% range from current: {ltp - one_pct:.0f} – {ltp + one_pct:.0f}

{ctx_txt}

Daily OHLC — last 60 trading days:
{ohlc_txt}

TASK: Using BOTH the price action data AND the global context above, find:
- Exactly 2 SUPPORT levels within 1% of current price {ltp:.0f} (i.e. between {ltp - one_pct:.0f} and {ltp:.0f})
- Exactly 2 RESISTANCE levels within 1% of current price {ltp:.0f} (i.e. between {ltp:.0f} and {ltp + one_pct:.0f})

Rules:
1. Level must have caused a SHARP bounce/rejection (1%+ move in 1 day) at least twice in the data.
2. If global context shows VIX spike, DXY strength or crude weakness — factor that into the bias.
3. If fewer than 2 clean levels exist within 1%, pick the nearest ones just outside 1% range.
4. DO NOT include levels where price just drifted through slowly.

valid_today = levels within 1% of current price {ltp:.0f}.

Respond ONLY in valid JSON (no markdown):
{{
  "supports": [{{"level": 0, "reason": "dates + reaction size, e.g. bounced +1.8% on May 11, Apr 28"}}],
  "resistances": [{{"level": 0, "reason": "dates + reaction size"}}],
  "valid_today": [{{"level": 0, "type": "support", "note": "..."}}],
  "verdict": "2 sentences: today's bias based on price action + global context, and which level to watch."
}}

Return exactly 2 supports and 2 resistances."""

    try:
        ac  = _anthropic.Anthropic()
        rsp = ac.messages.create(
            model='claude-haiku-4-5', max_tokens=1400,
            messages=[{'role': 'user', 'content': prompt}]
        )
        raw = rsp.content[0].text.strip()
        if raw.startswith('```'):
            raw = raw.split('```')[1]
            if raw.startswith('json'): raw = raw[4:]
        data = json.loads(raw.strip())
        data['ltp']     = ltp
        data['index']   = idx
        data['context'] = ctx.get('quotes', [])
        return jsonify(data)
    except json.JSONDecodeError as e:
        return jsonify({'error': f'Claude returned invalid JSON: {e}', 'raw': raw}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/save-sr', methods=['POST'])
def api_save_sr():
    client = require_auth()
    if not client:
        return jsonify({'error': 'Not authenticated'}), 401
    body = request.get_json() or {}
    try:
        rid = save_sr(
            index_id    = body.get('index', ''),
            ltp         = float(body.get('ltp', 0)),
            supports    = body.get('supports', []),
            resistances = body.get('resistances', []),
            valid_today = body.get('valid_today', []),
            verdict     = body.get('verdict', ''),
        )
        return jsonify({'success': True, 'id': rid})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/sr-levels-summary')
def api_sr_levels_summary():
    """Return latest saved S/R levels for ALL indices in one call."""
    client = require_auth()
    if not client:
        return jsonify({'error': 'Not authenticated'}), 401
    result = []
    for idx in INDICES:
        history = get_sr_history(idx['id'], limit=1)
        latest  = history[0] if history else None
        result.append({
            'id':          idx['id'],
            'label':       idx.get('label', idx['id']),
            'supports':    latest['supports']    if latest else [],
            'resistances': latest['resistances'] if latest else [],
            'ltp':         latest['ltp']         if latest else 0,
            'saved_at':    latest['saved_at']    if latest else '',
        })
    return jsonify({'indices': result})


@app.route('/api/sr-history')
def api_sr_history():
    client = require_auth()
    if not client:
        return jsonify({'error': 'Not authenticated'}), 401
    idx   = request.args.get('index', 'SENSEX').upper()
    limit = int(request.args.get('limit', 10))
    return jsonify({'history': get_sr_history(idx, limit)})


@app.route('/api/sr-history/<int:record_id>', methods=['DELETE'])
def api_delete_sr(record_id):
    client = require_auth()
    if not client:
        return jsonify({'error': 'Not authenticated'}), 401
    try:
        deleted = delete_sr(record_id)
        return jsonify({'success': True, 'deleted': deleted})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/debug-components')
def api_debug_components():
    """Debug: test single vs batch fetch_market_feed + verify scrip codes via search."""
    client = require_auth()
    if not client:
        return jsonify({'error': 'Not authenticated'}), 401

    # Auto-restore from saved session file if cookie missing
    if not client:
        from modules.auth import try_restore_session as _trs, authenticated_clients as _ac
        _cid = _trs()
        client = _ac.get(_cid) if _cid else None
    if not client:
        return jsonify({'error': 'No saved session on server — log in once via the dashboard first'}), 401

    results = {}

    # 1. Search master for correct scrip codes
    from modules.master import search_scrips
    for q in ['RELIANCE', 'HDFCBANK', 'INFY']:
        hits = search_scrips(q)
        results[f'search_{q}'] = hits[:5]

    # 2. Try single-item fetch_market_feed for first SENSEX component
    idx      = request.args.get('index', 'SENSEX').upper()
    cfg_comp = COMPONENTS.get(idx)
    if cfg_comp:
        comp = cfg_comp['components'][0]
        exch = cfg_comp['exch']
        et   = cfg_comp['exch_type']

        # Single item
        try:
            r1 = client.fetch_market_feed([{'Exch': exch, 'ExchangeType': et, 'ScripCode': int(comp['scrip_code'])}])
            results['single_item'] = {'scrip': comp['scrip_code'], 'name': comp['name'],
                                      'response': str(r1), 'type': type(r1).__name__}
        except Exception as e:
            results['single_item'] = {'error': str(e)}

        # Two items
        comps2 = cfg_comp['components'][:2]
        try:
            r2 = client.fetch_market_feed([{'Exch': exch, 'ExchangeType': et, 'ScripCode': int(c['scrip_code'])} for c in comps2])
            results['two_items'] = {'response': str(r2), 'type': type(r2).__name__}
        except Exception as e:
            results['two_items'] = {'error': str(e)}

    return jsonify(results)


@app.route('/api/components')
def api_components():
    client = require_auth()
    if not client:
        return jsonify({'error': 'Not authenticated'}), 401
    idx      = request.args.get('index', 'SENSEX').upper()
    cfg_comp = COMPONENTS.get(idx)
    if not cfg_comp:
        return jsonify({'error': f'No components configured for {idx}'}), 400
    return jsonify(get_components_ltp(
        client,
        cfg_comp['components'],
        cfg_comp['exch'],
        cfg_comp['exch_type'],
    ))


@app.route('/api/chain-analysis-history')
def api_chain_analysis_history():
    client = require_auth()
    if not client:
        return jsonify({'error': 'Not authenticated'}), 401
    idx   = request.args.get('index', 'SENSEX').upper()
    limit = int(request.args.get('limit', 20))
    return jsonify({'history': get_chain_analysis_history(idx, limit)})


@app.route('/api/chain-analysis-history/<int:record_id>', methods=['DELETE'])
def api_delete_chain_analysis(record_id):
    client = require_auth()
    if not client:
        return jsonify({'error': 'Not authenticated'}), 401
    deleted = delete_chain_analysis(record_id)
    return jsonify({'success': True, 'deleted': deleted})


@app.route('/api/market-update/last-sent')
def api_market_update_last_sent():
    client = require_auth()
    if not client:
        return jsonify({'error': 'Not authenticated'}), 401
    last = get_setting('market_update_last_sent', '')
    return jsonify({'last_sent': last})


@app.route('/api/market-update/config', methods=['GET'])
def api_market_update_config_get():
    client = require_auth()
    if not client:
        return jsonify({'error': 'Not authenticated'}), 401
    return jsonify({
        'enabled':      get_setting('market_update_enabled',      'false') == 'true',
        'freq_min':     int(get_setting('market_update_freq_min', '5')),
        'indices':      get_setting('market_update_indices',      'SENSEX,NIFTY,BANKNIFTY,FINNIFTY'),
        'market_hours': get_setting('market_update_market_hours', 'false') == 'true',
    })


@app.route('/api/market-update/config', methods=['POST'])
def api_market_update_config_set():
    client = require_auth()
    if not client:
        return jsonify({'error': 'Not authenticated'}), 401
    body     = request.get_json() or {}
    enabled  = bool(body.get('enabled', False))
    freq_min = int(body.get('freq_min', 5))
    indices      = body.get('indices', 'SENSEX,NIFTY,BANKNIFTY,FINNIFTY')
    market_hours = bool(body.get('market_hours', False))
    if freq_min not in (1, 2, 5, 10, 15):
        return jsonify({'error': 'freq_min must be 1, 2, 5, 10, or 15'}), 400
    set_setting('market_update_enabled',      'true' if enabled else 'false')
    set_setting('market_update_freq_min',     str(freq_min))
    set_setting('market_update_indices',      str(indices))
    set_setting('market_update_market_hours', 'true' if market_hours else 'false')
    try:
        from modules.scheduler import run_market_update
        if _scheduler.get_job('market_update'):
            _scheduler.remove_job('market_update')
        if enabled:
            _scheduler.add_job(run_market_update, 'interval', minutes=freq_min,
                               id='market_update', max_instances=1, misfire_grace_time=60)
    except Exception as e:
        return jsonify({'error': f'Scheduler update failed: {e}'}), 500
    return jsonify({'success': True, 'enabled': enabled, 'freq_min': freq_min,
                    'indices': indices, 'market_hours': market_hours})


@app.route('/api/place-order', methods=['POST'])
def api_place_order():
    client = require_auth()
    if not client:
        return jsonify({'error': 'Not authenticated'}), 401
    body       = request.get_json() or {}
    scrip_code = int(body.get('scrip_code', 0))
    exch       = body.get('exch', 'N')          # 'N' for NSE, 'B' for BSE
    qty        = int(body.get('qty', 0))
    if not scrip_code or qty <= 0:
        return jsonify({'error': 'scrip_code and qty are required'}), 400
    try:
        exch_type = 'D'   # Derivatives
        # 5paisa requires a LIMIT price for derivative orders (market orders rejected).
        # Use LTP + 2% as limit price so the buy fills immediately at market.
        ltp   = float(body.get('ltp', 0))
        price = round(ltp * 1.02, 2) if ltp > 0 else 0
        result = client.place_order(
            OrderType    = 'B',
            Exchange     = exch,
            ExchangeType = exch_type,
            ScripCode    = scrip_code,
            Qty          = qty,
            Price        = price,
            IsIntraday   = True,
            StopLossPrice = 0,
            IsIOCOrder   = False,
        )
        # Always log raw response for debugging
        print(f'[ORDER] raw response: {result!r}')

        if not isinstance(result, dict):
            # Some versions return a list or string — treat as unknown
            return jsonify({'success': False, 'error': 'Unexpected response format', 'raw': str(result)})

        # py5paisa: Status=0 means success, non-zero means error
        status   = result.get('Status', result.get('status', -1))
        message  = result.get('Message') or result.get('message') or ''
        order_id = (result.get('BrokerOrderId') or
                    result.get('OrderId') or
                    result.get('RemoteOrderID') or
                    result.get('order_id') or '')

        # Convert to int for reliable comparison (API returns int 0 on success)
        try:
            status_int = int(status)
        except (TypeError, ValueError):
            status_int = -1

        if status_int == 0 and order_id:
            return jsonify({'success': True, 'order_id': str(order_id),
                            'message': message, 'raw': result})
        else:
            # Include raw so frontend can show what actually came back
            error_msg = message or f'Status={status}'
            return jsonify({'success': False, 'error': error_msg, 'raw': result})

    except Exception as e:
        print(f'[ORDER] exception: {e}')
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/snapshots')
def api_snapshots():
    client = require_auth()
    if not client:
        return jsonify({'error': 'Not authenticated'}), 401
    idx   = request.args.get('index', 'SENSEX').upper()
    limit = int(request.args.get('limit', 60))
    return jsonify({'snapshots': get_snapshots(idx, limit)})


@app.route('/api/scheduler/status')
def api_scheduler_status():
    client = require_auth()
    if not client:
        return jsonify({'error': 'Not authenticated'}), 401
    try:
        job = _scheduler.get_job('sensex_snapshot')
        if not job:
            return jsonify({'running': False, 'next_run': None})
        paused   = job.next_run_time is None
        next_run = job.next_run_time.strftime('%H:%M:%S') if job.next_run_time else None
        # Last snapshot info
        snaps = get_snapshots('SENSEX', 1)
        last  = snaps[0] if snaps else {}
        return jsonify({
            'running':    not paused,
            'next_run':   next_run,
            'last_saved': last.get('saved_at', '—'),
            'last_ltp':   last.get('ltp', 0),
            'last_pcr':   last.get('pcr', 0),
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/scheduler/run-now')
def api_scheduler_run_now():
    """Force an immediate snapshot (ignores market hours) — for testing."""
    client = require_auth()
    if not client:
        return jsonify({'error': 'Not authenticated'}), 401
    import traceback
    try:
        from modules.auth import _restore_client
        from modules.market import get_expiry_dates, get_option_chain_data, get_index_ltp
        from modules.db import save_snapshot, cleanup_old_snapshots
        import anthropic as _ac
        from datetime import datetime, timezone, timedelta
        _IST = timezone(timedelta(hours=5, minutes=30))

        # Step 1: restore client
        rc = _restore_client()
        if not rc:
            return jsonify({'step': 'restore_client', 'error': 'No saved session — .5paisa_session.json missing or JWT expired'})

        # Step 2: expiries
        expiry_data = get_expiry_dates(rc, 'B', 'SENSEX')
        if 'error' in expiry_data or not expiry_data.get('expiries'):
            return jsonify({'step': 'expiries', 'error': str(expiry_data)})

        expiry     = expiry_data['expiries'][0]
        expiry_ts  = expiry['ts']
        expiry_lbl = expiry['label']

        # Step 3: LTP
        ltp_data   = get_index_ltp(rc, 'B', 999901, 'SENSEX')
        ltp        = ltp_data.get('ltp', 0)
        prev_close = ltp_data.get('prev_close', 0)
        change_abs = ltp_data.get('change', 0)
        change_pct = ltp_data.get('change_pct', 0)

        if ltp == 0:
            return jsonify({'step': 'ltp', 'error': 'LTP is 0', 'ltp_data': ltp_data})

        # Step 4: option chain
        chain = get_option_chain_data(rc, 'B', 'SENSEX', expiry_ts)
        if 'error' in chain or not chain.get('option_chain'):
            return jsonify({'step': 'chain', 'error': str(chain)})

        rows        = chain['option_chain']
        total_ce_oi = sum(r['ce_oi'] for r in rows)
        total_pe_oi = sum(r['pe_oi'] for r in rows)
        pcr         = round(total_pe_oi / total_ce_oi, 2) if total_ce_oi > 0 else 0
        max_pain    = max(rows, key=lambda r: r['ce_oi'] + r['pe_oi'], default={'strike':0})['strike']
        top_ce      = sorted(rows, key=lambda r: r['ce_oi'],  reverse=True)[:3]
        top_pe      = sorted(rows, key=lambda r: r['pe_oi'],  reverse=True)[:3]
        near_rows   = sorted(rows, key=lambda r: abs(r['strike'] - ltp))[:12]

        chain_txt = 'Strike|CE_OI|CE_ChgOI|PE_OI|PE_ChgOI\n'
        for r in near_rows:
            chain_txt += f"{int(r['strike'])}|{r['ce_oi']}|{r['ce_chg_oi']}|{r['pe_oi']}|{r['pe_chg_oi']}\n"

        # Step 5: AI summary
        prompt = f"""SENSEX option chain snapshot. Be brief and direct.
Price: {ltp} | Change: {change_abs:+.0f} ({change_pct:+.2f}%) | Expiry: {expiry_lbl}
PCR: {pcr} | Max Pain: {int(max_pain)}
Top CE resistance: {', '.join(str(int(r['strike'])) for r in top_ce)}
Top PE support: {', '.join(str(int(r['strike'])) for r in top_pe)}
{chain_txt}
In 80 words max: (1) Bias bullish/bearish/neutral + reason, (2) Key support, (3) Key resistance, (4) Watch out for."""

        ac  = _ac.Anthropic()
        rsp = ac.messages.create(model='claude-haiku-4-5', max_tokens=250,
                                 messages=[{'role':'user','content':prompt}])
        summary = rsp.content[0].text.strip()

        save_snapshot(index_id='SENSEX', expiry_label=expiry_lbl, expiry_ts=expiry_ts,
                      ltp=ltp, prev_close=prev_close, change_abs=change_abs,
                      change_pct=change_pct, pcr=pcr, max_pain=max_pain,
                      ce_oi=total_ce_oi, pe_oi=total_pe_oi, summary=summary)

        return jsonify({'ok': True, 'ltp': ltp, 'pcr': pcr, 'max_pain': max_pain,
                        'expiry': expiry_lbl, 'summary': summary})
    except Exception as e:
        return jsonify({'error': str(e), 'trace': traceback.format_exc()}), 500


@app.route('/api/scheduler/toggle', methods=['POST'])
def api_scheduler_toggle():
    client = require_auth()
    if not client:
        return jsonify({'error': 'Not authenticated'}), 401
    try:
        job    = _scheduler.get_job('sensex_snapshot')
        paused = job.next_run_time is None
        if paused:
            _scheduler.resume_job('sensex_snapshot')
            return jsonify({'running': True})
        else:
            _scheduler.pause_job('sensex_snapshot')
            return jsonify({'running': False})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── DB Browser API ─────────────────────────────────────────────────────────────

_ALLOWED_TABLES = {
    'sr_levels', 'chain_snapshots', 'chain_analysis',
    'sr_alerts', 'breach_alerts', 'settings', 'market_summary', 'trade_watchlist',
}

def _db_conn():
    import sqlite3
    _DB_PATH = os.path.join(os.path.dirname(__file__), 'dashboard.db')
    c = sqlite3.connect(_DB_PATH)
    c.row_factory = sqlite3.Row
    return c


@app.route('/api/db/tables')
def api_db_tables():
    if not require_auth():
        return jsonify({'error': 'Not authenticated'}), 401
    try:
        with _db_conn() as c:
            rows = c.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
            result = []
            for r in rows:
                name = r['name']
                cnt  = c.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
                result.append({'name': name, 'count': cnt})
        return jsonify({'tables': result})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/db/records')
def api_db_records():
    if not require_auth():
        return jsonify({'error': 'Not authenticated'}), 401
    table = request.args.get('table', '').strip()
    if table not in _ALLOWED_TABLES:
        return jsonify({'error': f'Table "{table}" not allowed'}), 400
    limit  = min(int(request.args.get('limit',  2000)), 5000)
    offset = int(request.args.get('offset', 0))
    try:
        with _db_conn() as c:
            rows = c.execute(
                f'SELECT * FROM "{table}" ORDER BY rowid DESC LIMIT ? OFFSET ?',
                (limit, offset)
            ).fetchall()
            if not rows:
                return jsonify({'columns': [], 'rows': [], 'total': 0})
            columns = list(rows[0].keys())
            data    = [dict(r) for r in rows]
        return jsonify({'columns': columns, 'rows': data})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/db/records', methods=['DELETE'])
def api_db_delete_record():
    if not require_auth():
        return jsonify({'error': 'Not authenticated'}), 401
    table = request.args.get('table', '').strip()
    rid   = request.args.get('id', '')
    if table not in _ALLOWED_TABLES:
        return jsonify({'error': f'Table "{table}" not allowed'}), 400
    if not rid:
        return jsonify({'error': 'id is required'}), 400
    if table == 'settings':
        return jsonify({'error': 'Cannot delete settings rows — edit the value instead'}), 400
    try:
        with _db_conn() as c:
            c.execute(f'DELETE FROM "{table}" WHERE id = ?', (rid,))
            c.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/db/truncate', methods=['POST'])
def api_db_truncate():
    if not require_auth():
        return jsonify({'error': 'Not authenticated'}), 401
    body  = request.get_json() or {}
    table = body.get('table', '').strip()
    if table not in _ALLOWED_TABLES:
        return jsonify({'error': f'Table "{table}" not allowed'}), 400
    if table == 'settings':
        return jsonify({'error': 'Cannot truncate settings table'}), 400
    try:
        with _db_conn() as c:
            c.execute(f'DELETE FROM "{table}"')
            c.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/log')
def view_log():
    lines = list(_mem_handler.buf)
    # colour-code by level
    def _cls(line):
        if 'ERROR' in line or '❌' in line:  return 'err'
        if 'WARNING' in line or '⚠' in line: return 'warn'
        if '✅' in line or 'SUCCESS' in line: return 'ok'
        if '[TRADE' in line or '[SL_' in line or '[SCHED' in line: return 'trade'
        if '[SNAP' in line or '[MARKET' in line: return 'snap'
        return ''
    rows = ''.join(
        f'<div class="ln {_cls(l)}">{l}</div>'
        for l in reversed(lines)   # newest first
    )
    count = len(lines)
    return f'''<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>App Log</title>
<meta http-equiv="refresh" content="10">
<style>
  body  {{ background:#0d0d1a; color:#94a3b8; font:12px/1.5 "Cascadia Code","Fira Mono",monospace; margin:0; padding:0; }}
  .top  {{ position:sticky; top:0; background:#12111f; border-bottom:1px solid #2d2b4e;
           padding:10px 18px; display:flex; gap:14px; align-items:center; z-index:9; }}
  .top h1 {{ margin:0; font-size:1em; color:#e2e8f0; }}
  .badge {{ background:#1e1b4b; color:#a78bfa; border-radius:20px; padding:2px 10px; font-size:0.85em; }}
  .refresh {{ color:#4b5563; font-size:0.78em; }}
  .copy {{ background:#4c1d95; color:#e2e8f0; border:none; border-radius:6px;
           padding:4px 12px; cursor:pointer; font-size:0.82em; margin-left:auto; }}
  .copy:hover {{ background:#5b21b6; }}
  .log  {{ padding:10px 18px 40px; }}
  .ln   {{ padding:2px 0; border-bottom:1px solid #12111f; white-space:pre-wrap; word-break:break-all; }}
  .err  {{ color:#f87171; }}
  .warn {{ color:#fbbf24; }}
  .ok   {{ color:#34d399; }}
  .trade{{ color:#818cf8; }}
  .snap {{ color:#60a5fa; }}
</style>
</head>
<body>
<div class="top">
  <h1>📋 App Log</h1>
  <span class="badge">{count} lines</span>
  <span class="refresh">auto-refresh 10s</span>
  <button class="copy" onclick="copyAll()">📋 Copy All</button>
  <a href="/log" style="color:#6b7280;font-size:0.8em;text-decoration:none">↻ Refresh</a>
</div>
<div class="log" id="logbox">{rows or '<div style="color:#4b5563;padding:20px">No log entries yet.</div>'}</div>
<script>
function copyAll() {{
  const text = Array.from(document.querySelectorAll('.ln')).map(e=>e.textContent).join('\\n');
  navigator.clipboard.writeText(text).then(()=>{{ const b=document.querySelector('.copy'); b.textContent='✅ Copied!'; setTimeout(()=>b.textContent='📋 Copy All',1500); }});
}}
</script>
</body>
</html>'''


@app.route('/log/json')
def view_log_json():
    """Raw JSON log dump for programmatic access."""
    return json.dumps(list(_mem_handler.buf)), 200, {'Content-Type': 'application/json'}


if __name__ == '__main__':
    import threading
    def _preload():
        from modules.master import load_master
        try:
            load_master()
            print("[MASTER] Scrip master loaded")
        except Exception as e:
            print(f"[MASTER] Load failed: {e}")
    threading.Thread(target=_preload, daemon=True).start()
    _port = int(os.getenv("PORT", 3000))
    print("[START] 5Paisa Dashboard")
    print(f"[URL]   http://0.0.0.0:{_port}")
    app.run(host='0.0.0.0', port=_port, debug=False)

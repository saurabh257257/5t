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
from modules.db import init_db, save_sr, get_sr_history, delete_sr, get_snapshots

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
    _scheduler.start()
    print('[SCHEDULER] Started — SENSEX snapshots every 1 min during market hours')
except Exception as _e:
    print(f'[SCHEDULER] Failed to start: {_e}')

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "5paisa-flask-secret")
app.config['PERMANENT_SESSION_LIFETIME'] = __import__('datetime').timedelta(days=30)

PIN = os.getenv("APP_PIN", "7592")
DROPLET_IP = os.getenv("DROPLET_IP", "142.93.222.101")


def require_auth():
    # 1. Fast path — client already in memory
    cid = session.get('client_id')
    if cid:
        client = authenticated_clients.get(cid)
        if client:
            return client

    # 2. Slow path — server restarted OR browser cookie gone
    #    Try to restore from the saved JWT file on disk
    restored_cid = try_restore_session()
    if restored_cid:
        session.permanent = True          # cookie survives browser close
        session['client_id'] = restored_cid
        return authenticated_clients.get(restored_cid)

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
    cid = session.pop('client_id', None)
    if cid:
        authenticated_clients.pop(cid, None)
    session.clear()
    return redirect('/')


# ── Pages ──────────────────────────────────────────────────────────────────────

@app.route('/dashboard')
def dashboard():
    if not require_auth():
        return redirect('/')
    return render_template('dashboard.html')


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
    return jsonify(get_index_ltp(client, cfg['feed_exch'], cfg['feed_scrip'], cfg['opt_symbol']))


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

    # Max pain — strike with highest total OI
    max_pain = max(rows, key=lambda r: r['ce_oi'] + r['pe_oi'], default={}).get('strike', 0)

    # Highest CE & PE OI strikes (resistance / support)
    top_ce = sorted(rows, key=lambda r: r['ce_oi'], reverse=True)[:3]
    top_pe = sorted(rows, key=lambda r: r['pe_oi'], reverse=True)[:3]

    # 15 strikes nearest to LTP for detailed analysis
    near_rows = sorted(rows, key=lambda r: abs(r['strike'] - ltp))[:15]
    chain_txt = "Strike | CE_LTP | CE_OI | CE_ChgOI | CE_Vol | PE_LTP | PE_OI | PE_ChgOI | PE_Vol\n"
    for r in near_rows:
        chain_txt += (f"{int(r['strike'])} | {r['ce_ltp']} | {r['ce_oi']} | {r['ce_chg_oi']} | "
                      f"{r['ce_vol']} | {r['pe_ltp']} | {r['pe_oi']} | {r['pe_chg_oi']} | {r['pe_vol']}\n")

    chg_pct = round((ltp - prev_close) / prev_close * 100, 2) if prev_close > 0 else 0
    chg_abs = round(ltp - prev_close, 2)

    prompt = f"""You are an expert options trader. Analyze this {idx} option chain and provide a market summary.

Index: {idx}  |  Expiry: {expiry_lbl}
Current Price: {ltp}  |  Prev Close: {prev_close}  |  Change: {chg_abs:+.2f} ({chg_pct:+.2f}%)
PCR (PE OI / CE OI): {pcr}  |  Max Pain: {int(max_pain)}
Top CE OI (resistance): {', '.join(str(int(r['strike'])) for r in top_ce)}
Top PE OI (support): {', '.join(str(int(r['strike'])) for r in top_pe)}

Option Chain (15 strikes near current price):
{chain_txt}
Provide analysis in exactly these sections:
1. **Market Bias** — bullish/bearish/neutral, one clear reason
2. **Key Support** — top 2 PE OI levels protecting downside
3. **Key Resistance** — top 2 CE OI levels capping upside
4. **PCR Signal** — what {pcr} PCR means for market sentiment
5. **Max Pain** — implication of {int(max_pain)} max pain vs current {ltp}
6. **Watch Out** — any unusual OI buildup, unwinding, or red flags

Max 220 words. Be specific with levels."""

    try:
        ac = _anthropic.Anthropic()
        resp = ac.messages.create(
            model="claude-haiku-4-5",
            max_tokens=700,
            messages=[{"role": "user", "content": prompt}]
        )
        return jsonify({
            "summary":      resp.content[0].text,
            "pcr":          pcr,
            "max_pain":     max_pain,
            "total_ce_oi":  total_ce_oi,
            "total_pe_oi":  total_pe_oi,
            "change":       chg_abs,
            "change_pct":   chg_pct,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


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
    return jsonify(get_today_ohlc(client, cfg['feed_exch'], cfg['feed_scrip']))


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
    return jsonify(get_chart_data(client, cfg['feed_exch'], cfg['feed_scrip'], interval, days))


@app.route('/api/analyze-sr')
def api_analyze_sr():
    client = require_auth()
    if not client:
        return jsonify({'error': 'Not authenticated'}), 401
    idx = request.args.get('index', 'SENSEX').upper()
    if idx not in INDEX_MAP:
        return jsonify({'error': f'Unknown index: {idx}'}), 400
    cfg = INDEX_MAP[idx]

    # Fetch 1-year daily candles
    chart = get_chart_data(client, cfg['feed_exch'], cfg['feed_scrip'], interval='1d', days=380)
    if 'error' in chart or not chart.get('candles'):
        return jsonify({'error': 'Could not fetch historical data for S/R analysis'})

    candles = chart['candles']
    ltp     = candles[-1]['close'] if candles else 0

    # Build last 60 days OHLC text for the prompt
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

    prompt = f"""You are an expert technical analyst for Indian markets.

Index: {idx}  |  Current Price: {ltp:.0f}
52-Week High: {yr_high:.0f}  |  52-Week Low: {yr_low:.0f}

Daily OHLC — last 60 trading days (use 1-year context for patterns):
{ohlc_txt}

Identify 3-5 key SUPPORT and 3-5 key RESISTANCE levels based on:
- Major swing highs/lows with multiple touches
- Round numbers that acted as S/R
- 52-week high/low
- Consolidation zones and breakout/breakdown levels

valid_today = levels within 2% of current price {ltp:.0f}.

Respond ONLY in valid JSON (no markdown, no explanation outside JSON):
{{
  "supports": [{{"level": 0, "strength": "strong", "reason": "..."}}],
  "resistances": [{{"level": 0, "strength": "strong", "reason": "..."}}],
  "valid_today": [{{"level": 0, "type": "support", "note": "..."}}],
  "verdict": "2-3 sentence technical outlook for today."
}}

strength values: "strong" (3+ tests), "moderate" (2 tests), "weak" (1 test/confluence)"""

    try:
        ac  = _anthropic.Anthropic()
        rsp = ac.messages.create(
            model='claude-haiku-4-5', max_tokens=1200,
            messages=[{'role': 'user', 'content': prompt}]
        )
        raw = rsp.content[0].text.strip()
        if raw.startswith('```'):
            raw = raw.split('```')[1]
            if raw.startswith('json'): raw = raw[4:]
        data = json.loads(raw.strip())
        data['ltp']   = ltp
        data['index'] = idx
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
    print("[START] 5Paisa Dashboard")
    print("[URL]   http://0.0.0.0:3000")
    app.run(host='0.0.0.0', port=3000, debug=False)

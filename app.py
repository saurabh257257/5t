from flask import Flask, request, session, redirect, jsonify, render_template
import os
import anthropic as _anthropic
from dotenv import load_dotenv
from modules.auth import process_callback, authenticated_clients, cred
from modules.holdings import get_holdings_data
from modules.master import search_scrips, refresh_master, get_scrip_info, browse_scrips, get_status
from modules.market import get_ltp, get_expiry_dates, get_option_chain_data, get_sensex_ltp, get_historical_data

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "5paisa-flask-secret")

PIN = os.getenv("APP_PIN", "7592")
DROPLET_IP = os.getenv("DROPLET_IP", "142.93.222.101")


def require_auth():
    cid = session.get('client_id')
    return authenticated_clients.get(cid) if cid else None


# ── Auth routes ────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    if require_auth():
        return redirect('/dashboard')
    return render_template('pin.html', error=None)


@app.route('/verify-pin', methods=['POST'])
def verify_pin():
    if request.form.get('pin', '').strip() == PIN:
        session['pin_verified'] = True
        login_url = (
            f"https://dev-openapi.5paisa.com/WebVendorLogin/VLogin/Index"
            f"?VendorKey={cred['USER_KEY']}"
            f"&ResponseURL=http://{DROPLET_IP}:3000/callback"
        )
        return render_template('login.html', login_url=login_url)
    return render_template('pin.html', error="Incorrect PIN. Please try again.")


@app.route('/callback')
def callback():
    result = process_callback(request.args)
    if result['success']:
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
    return jsonify(get_expiry_dates(
        client,
        request.args.get('exch', 'N'),
        request.args.get('symbol', '')
    ))


@app.route('/api/sensex-ltp')
def api_sensex_ltp():
    client = require_auth()
    if not client:
        return jsonify({"error": "Not authenticated"}), 401
    return jsonify(get_sensex_ltp(client))


@app.route('/api/option-chain')
def api_option_chain():
    client = require_auth()
    if not client:
        return jsonify({"error": "Not authenticated"}), 401
    return jsonify(get_option_chain_data(
        client,
        request.args.get('exch', 'N'),
        request.args.get('symbol', ''),
        request.args.get('expiry_ts', 0)
    ))


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
            model="claude-opus-4-7",
            max_tokens=700,
            messages=[{"role": "user", "content": prompt}]
        )
        return jsonify({"summary": resp.content[0].text})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


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

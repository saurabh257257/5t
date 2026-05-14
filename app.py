from flask import Flask, request, session, redirect, jsonify, render_template
import os
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
        request.args.get('interval', '1m')
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

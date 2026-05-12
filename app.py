from flask import Flask, request, session, redirect, jsonify, render_template_string
from py5paisa import FivePaisaClient
import os
import uuid
import secrets
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "5paisa-flask-secret")

PIN = os.getenv("APP_PIN", "7592")
DROPLET_IP = os.getenv("DROPLET_IP", "167.71.237.92")

cred = {
    "APP_NAME": os.getenv("APP_NAME", "5P58004979"),
    "APP_SOURCE": os.getenv("APP_SOURCE", "24930"),
    "USER_ID": os.getenv("USER_ID", "47xt4VnND2x"),
    "PASSWORD": os.getenv("PASSWORD", "B356hBPBrAK"),
    "USER_KEY": os.getenv("USER_KEY", "PyA72PuyUjYUiNavyRlN0bdLnc7aFeKp"),
    "ENCRYPTION_KEY": os.getenv("ENCRYPTION_KEY", "wnzELKnWbdH3KYdgAyW0EwLdVpnk2O1D")
}

authenticated_clients = {}
pending_states = {}  # state_token -> True, for mobile OAuth flow

PIN_PAGE = '''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>5Paisa - Enter PIN</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .card {
            background: white;
            border-radius: 16px;
            padding: 48px 40px;
            width: 360px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            text-align: center;
        }
        .logo { font-size: 2.5em; margin-bottom: 12px; }
        h1 { font-size: 1.5em; color: #333; margin-bottom: 8px; }
        p { color: #888; margin-bottom: 32px; font-size: 0.95em; }
        input[type="password"] {
            width: 100%;
            padding: 16px;
            font-size: 1.4em;
            border: 2px solid #e5e7eb;
            border-radius: 10px;
            text-align: center;
            letter-spacing: 10px;
            outline: none;
            transition: border-color 0.2s;
        }
        input[type="password"]:focus { border-color: #667eea; }
        button {
            width: 100%;
            padding: 14px;
            background: #667eea;
            color: white;
            border: none;
            border-radius: 10px;
            font-size: 1em;
            font-weight: 600;
            cursor: pointer;
            margin-top: 16px;
            transition: background 0.2s;
        }
        button:hover { background: #5568d3; }
        .error {
            color: #ef4444;
            background: #fef2f2;
            border: 1px solid #fecaca;
            border-radius: 8px;
            padding: 10px;
            margin-top: 16px;
            font-size: 0.9em;
        }
    </style>
</head>
<body>
    <div class="card">
        <div class="logo">&#x1F4BC;</div>
        <h1>5Paisa Holdings</h1>
        <p>Enter your PIN to continue</p>
        <form method="POST" action="/verify-pin">
            <input type="password" name="pin" placeholder="••••" maxlength="10" autofocus />
            <button type="submit">Continue &rarr;</button>
        </form>
        {% if error %}
        <div class="error">{{ error }}</div>
        {% endif %}
    </div>
</body>
</html>'''

LOGIN_PAGE = '''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>5Paisa - Authorize</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .card {
            background: white;
            border-radius: 16px;
            padding: 48px 40px;
            width: 420px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            text-align: center;
        }
        .logo { font-size: 2.5em; margin-bottom: 12px; }
        h1 { font-size: 1.4em; color: #333; margin-bottom: 12px; }
        p { color: #888; margin-bottom: 32px; font-size: 0.95em; line-height: 1.6; }
        a.btn {
            display: block;
            padding: 16px;
            background: #667eea;
            color: white;
            border-radius: 10px;
            font-size: 1em;
            font-weight: 600;
            text-decoration: none;
            transition: background 0.2s;
        }
        a.btn:hover { background: #5568d3; }
        .note {
            margin-top: 20px;
            color: #aaa;
            font-size: 0.82em;
        }
    </style>
</head>
<body>
    <div class="card">
        <div class="logo">&#x1F510;</div>
        <h1>Authorize with 5Paisa</h1>
        <p>Click the button below to log in with your 5Paisa account. You will be redirected back automatically after login.</p>
        <a class="btn" href="{{ login_url }}">Login with 5Paisa &rarr;</a>
        <div class="note">You will be redirected back to this app after login.</div>
    </div>
</body>
</html>'''

HOLDINGS_PAGE = '''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>5Paisa Holdings</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 24px;
        }
        .container { max-width: 1100px; margin: 0 auto; }
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 28px;
            color: white;
        }
        header h1 { font-size: 1.8em; }
        header p { font-size: 0.9em; opacity: 0.85; margin-top: 4px; }
        .header-right { display: flex; gap: 12px; align-items: center; }
        .btn-refresh, .btn-logout {
            padding: 9px 18px;
            border: none;
            border-radius: 8px;
            font-weight: 600;
            cursor: pointer;
            font-size: 0.9em;
        }
        .btn-refresh { background: white; color: #667eea; }
        .btn-refresh:hover { background: #f0f0ff; }
        .btn-logout { background: rgba(255,255,255,0.2); color: white; }
        .btn-logout:hover { background: rgba(255,255,255,0.3); }
        .card {
            background: white;
            border-radius: 12px;
            padding: 28px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.15);
            margin-bottom: 24px;
        }
        .summary {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }
        .stat {
            background: #f8f9ff;
            border-radius: 10px;
            padding: 18px;
            text-align: center;
        }
        .stat-label { color: #888; font-size: 0.8em; text-transform: uppercase; letter-spacing: 0.5px; }
        .stat-value { font-size: 1.5em; font-weight: 700; color: #333; margin-top: 4px; }
        .stat-value.profit { color: #10b981; }
        .stat-value.loss { color: #ef4444; }
        table { width: 100%; border-collapse: collapse; }
        thead { background: #f8f9ff; }
        th { padding: 12px 14px; text-align: left; font-size: 0.82em; color: #888; text-transform: uppercase; letter-spacing: 0.5px; border-bottom: 1px solid #eee; }
        td { padding: 14px; border-bottom: 1px solid #f0f0f0; color: #444; font-size: 0.95em; }
        tr:last-child td { border-bottom: none; }
        tr:hover td { background: #fafafa; }
        .symbol { font-weight: 700; color: #333; }
        .profit { color: #10b981; font-weight: 600; }
        .loss { color: #ef4444; font-weight: 600; }
        .loading { text-align: center; padding: 48px; color: #aaa; }
        .spinner {
            border: 3px solid #f0f0f0;
            border-top: 3px solid #667eea;
            border-radius: 50%;
            width: 36px; height: 36px;
            animation: spin 0.8s linear infinite;
            margin: 0 auto 12px;
        }
        @keyframes spin { to { transform: rotate(360deg); } }
        .empty { text-align: center; padding: 48px; color: #aaa; font-size: 0.95em; }
        .error-msg { text-align: center; padding: 24px; color: #ef4444; }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div>
                <h1>&#x1F4BC; 5Paisa Holdings</h1>
                <p>Real-time Portfolio Tracker</p>
            </div>
            <div class="header-right">
                <button class="btn-refresh" onclick="loadHoldings()">&#x21BB; Refresh</button>
                <a href="/logout"><button class="btn-logout">Logout</button></a>
            </div>
        </header>

        <div class="summary" id="summary" style="display:none">
            <div class="stat">
                <div class="stat-label">Total Invested</div>
                <div class="stat-value" id="stat-invested">-</div>
            </div>
            <div class="stat">
                <div class="stat-label">Current Value</div>
                <div class="stat-value" id="stat-value">-</div>
            </div>
            <div class="stat">
                <div class="stat-label">Total P&amp;L</div>
                <div class="stat-value" id="stat-pnl">-</div>
            </div>
            <div class="stat">
                <div class="stat-label">Return</div>
                <div class="stat-value" id="stat-return">-</div>
            </div>
        </div>

        <div class="card">
            <div id="holdings">
                <div class="loading">
                    <div class="spinner"></div>
                    Loading your holdings...
                </div>
            </div>
        </div>
    </div>

    <script>
        async function loadHoldings() {
            document.getElementById('holdings').innerHTML = `
                <div class="loading">
                    <div class="spinner"></div>
                    Loading your holdings...
                </div>`;
            document.getElementById('summary').style.display = 'none';

            try {
                const res = await fetch('/api/holdings');
                const data = await res.json();

                if (data.error) {
                    document.getElementById('holdings').innerHTML =
                        `<div class="error-msg">Error: ${data.error}</div>`;
                    return;
                }

                if (!data.holdings || data.holdings.length === 0) {
                    document.getElementById('holdings').innerHTML =
                        `<div class="empty">No holdings found in this account.</div>`;
                    return;
                }

                let totalInvested = 0, totalValue = 0;

                let rows = data.holdings.map(h => {
                    const val = h.quantity * h.ltp;
                    const cost = h.quantity * h.cost;
                    const pnl = val - cost;
                    const ret = cost > 0 ? ((pnl / cost) * 100).toFixed(2) : '0.00';
                    totalInvested += cost;
                    totalValue += val;

                    const cls = pnl >= 0 ? 'profit' : 'loss';
                    return `
                        <tr>
                            <td class="symbol">${h.symbol}</td>
                            <td>${h.quantity}</td>
                            <td>&#8377;${h.cost.toFixed(2)}</td>
                            <td>&#8377;${h.ltp.toFixed(2)}</td>
                            <td>&#8377;${val.toFixed(2)}</td>
                            <td class="${cls}">&#8377;${pnl.toFixed(2)}</td>
                            <td class="${cls}">${ret}%</td>
                        </tr>`;
                }).join('');

                document.getElementById('holdings').innerHTML = `
                    <table>
                        <thead>
                            <tr>
                                <th>Symbol</th><th>Qty</th><th>Avg Cost</th>
                                <th>LTP</th><th>Current Value</th><th>P&amp;L</th><th>Return %</th>
                            </tr>
                        </thead>
                        <tbody>${rows}</tbody>
                    </table>`;

                const totalPnl = totalValue - totalInvested;
                const totalRet = totalInvested > 0 ? ((totalPnl / totalInvested) * 100).toFixed(2) : '0.00';
                const pnlCls = totalPnl >= 0 ? 'profit' : 'loss';

                document.getElementById('stat-invested').innerHTML = '&#8377;' + totalInvested.toFixed(2);
                document.getElementById('stat-value').innerHTML = '&#8377;' + totalValue.toFixed(2);
                document.getElementById('stat-pnl').className = 'stat-value ' + pnlCls;
                document.getElementById('stat-pnl').innerHTML = (totalPnl >= 0 ? '+' : '') + '&#8377;' + totalPnl.toFixed(2);
                document.getElementById('stat-return').className = 'stat-value ' + pnlCls;
                document.getElementById('stat-return').innerHTML = (totalPnl >= 0 ? '+' : '') + totalRet + '%';
                document.getElementById('summary').style.display = 'grid';

            } catch (err) {
                document.getElementById('holdings').innerHTML =
                    `<div class="error-msg">Failed to load: ${err.message}</div>`;
            }
        }

        window.addEventListener('load', loadHoldings);
        setInterval(loadHoldings, 60000);
    </script>
</body>
</html>'''


@app.route('/')
def index():
    if session.get('authenticated') and session.get('client_id') in authenticated_clients:
        return redirect('/holdings')
    return render_template_string(PIN_PAGE, error=None)


@app.route('/verify-pin', methods=['POST'])
def verify_pin():
    pin = request.form.get('pin', '').strip()
    if pin == PIN:
        state = secrets.token_urlsafe(24)
        pending_states[state] = True
        session['pin_verified'] = True
        callback_url = f"http://{DROPLET_IP}:3000/callback?state={state}"
        login_url = (
            f"https://dev-openapi.5paisa.com/WebVendorLogin/VLogin/Index"
            f"?VendorKey={cred['USER_KEY']}"
            f"&ResponseURL={callback_url}"
        )
        return render_template_string(LOGIN_PAGE, login_url=login_url)
    return render_template_string(PIN_PAGE, error="Incorrect PIN. Please try again.")


@app.route('/callback')
def callback():
    state = request.args.get('state')
    valid = pending_states.pop(state, False) if state else False
    if not valid and not session.get('pin_verified'):
        return redirect('/')

    request_token = request.args.get('RequestToken') or request.args.get('requestToken')
    if not request_token:
        return render_template_string(PIN_PAGE, error="Login failed: no token received.")

    try:
        c = FivePaisaClient(cred=cred)
        c.get_oauth_session(request_token)
        client_id = str(uuid.uuid4())
        authenticated_clients[client_id] = c
        session['authenticated'] = True
        session['client_id'] = client_id
        session.pop('pin_verified', None)
        return redirect('/holdings')
    except Exception as e:
        return render_template_string(PIN_PAGE, error=f"Auth failed: {str(e)}")


@app.route('/holdings')
def holdings():
    if not session.get('authenticated') or session.get('client_id') not in authenticated_clients:
        return redirect('/')
    return render_template_string(HOLDINGS_PAGE)


@app.route('/api/holdings')
def get_holdings():
    client_id = session.get('client_id')
    if not client_id or client_id not in authenticated_clients:
        return jsonify({"error": "Not authenticated"}), 401

    c = authenticated_clients[client_id]
    try:
        data = c.holdings()
        if not data:
            return jsonify({"holdings": []})

        result = []
        for h in data:
            result.append({
                "symbol": h.get("Symbol") or h.get("symbol", "N/A"),
                "quantity": int(h.get("Quantity") or h.get("quantity", 0)),
                "cost": float(h.get("AvgRate") or h.get("cost", 0)),
                "ltp": float(h.get("LTP") or h.get("ltp", 0))
            })
        return jsonify({"holdings": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/logout')
def logout():
    client_id = session.pop('client_id', None)
    if client_id:
        authenticated_clients.pop(client_id, None)
    session.clear()
    return redirect('/')


if __name__ == '__main__':
    print("[START] 5Paisa Holdings Server")
    print("[URL] http://0.0.0.0:3000")
    app.run(host='0.0.0.0', port=3000, debug=False)

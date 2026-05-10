from flask import Flask, render_template_string, jsonify
from py5paisa import FivePaisaClient
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# 5Paisa Credentials
cred = {
    "APP_NAME": os.getenv("APP_NAME", "5P58004979"),
    "APP_SOURCE": os.getenv("APP_SOURCE", "24930"),
    "USER_ID": os.getenv("USER_ID", "47xt4VnND2x"),
    "PASSWORD": os.getenv("PASSWORD", "B356hBPBrAK"),
    "USER_KEY": os.getenv("USER_KEY", "PyA72PuyUjYUiNavyRlN0bdLnc7aFeKp"),
    "ENCRYPTION_KEY": os.getenv("ENCRYPTION_KEY", "wnzELKnWbdH3KYdgAyW0EwLdVpnk2O1D")
}

try:
    client = FivePaisaClient(cred=cred)
    print("[OK] 5Paisa Connected")
except Exception as e:
    print(f"[ERROR] {e}")
    client = None

HTML = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>5Paisa Holdings</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container { max-width: 1200px; margin: 0 auto; }
        header {
            color: white;
            text-align: center;
            margin-bottom: 30px;
        }
        header h1 { font-size: 2.5em; margin-bottom: 10px; }

        .card {
            background: white;
            border-radius: 10px;
            padding: 25px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            margin-bottom: 30px;
        }

        .card-title {
            font-size: 1.5em;
            font-weight: bold;
            color: #333;
            margin-bottom: 20px;
            border-bottom: 2px solid #667eea;
            padding-bottom: 10px;
        }

        table {
            width: 100%;
            border-collapse: collapse;
        }

        table thead {
            background: #f0f0f0;
            border-bottom: 2px solid #ddd;
        }

        table th {
            padding: 12px;
            text-align: left;
            font-weight: bold;
            color: #333;
        }

        table td {
            padding: 12px;
            border-bottom: 1px solid #eee;
            color: #666;
        }

        table tr:hover { background: #f9f9f9; }

        .profit { color: #10b981; font-weight: bold; }
        .loss { color: #ef4444; font-weight: bold; }

        .loading {
            text-align: center;
            padding: 40px;
            color: #667eea;
        }

        .spinner {
            border: 4px solid #f0f0f0;
            border-top: 4px solid #667eea;
            border-radius: 50%;
            width: 40px;
            height: 40px;
            animation: spin 1s linear infinite;
            margin: 0 auto 10px;
        }

        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }

        button {
            background: #667eea;
            color: white;
            padding: 10px 20px;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            font-weight: bold;
        }

        button:hover { background: #5568d3; }

        .empty {
            text-align: center;
            padding: 40px;
            color: #999;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>💼 5Paisa Holdings</h1>
            <p>Real-time Portfolio Tracker</p>
        </header>

        <div class="card">
            <button onclick="loadHoldings()">🔄 Refresh Holdings</button>
        </div>

        <div class="card">
            <div class="card-title">📊 Your Holdings</div>
            <div id="holdings">
                <div class="loading">
                    <div class="spinner"></div>
                    Loading holdings...
                </div>
            </div>
        </div>
    </div>

    <script>
        async function loadHoldings() {
            try {
                const response = await fetch('/api/holdings');
                const data = await response.json();

                if (data.error) {
                    document.getElementById('holdings').innerHTML =
                        `<div class="empty">❌ ${data.error}</div>`;
                    return;
                }

                if (!data.holdings || data.holdings.length === 0) {
                    document.getElementById('holdings').innerHTML =
                        `<div class="empty">📭 No holdings found</div>`;
                    return;
                }

                let html = `
                    <table>
                        <thead>
                            <tr>
                                <th>Symbol</th>
                                <th>Quantity</th>
                                <th>Cost Price</th>
                                <th>Current Price</th>
                                <th>Total Value</th>
                                <th>P&L</th>
                                <th>Return %</th>
                            </tr>
                        </thead>
                        <tbody>
                `;

                data.holdings.forEach(h => {
                    const value = h.quantity * h.ltp;
                    const cost = h.quantity * h.cost;
                    const pnl = value - cost;
                    const ret = ((pnl / cost) * 100).toFixed(2);
                    const pnlClass = pnl >= 0 ? 'profit' : 'loss';

                    html += `
                        <tr>
                            <td><strong>${h.symbol}</strong></td>
                            <td>${h.quantity}</td>
                            <td>₹${h.cost.toFixed(2)}</td>
                            <td>₹${h.ltp.toFixed(2)}</td>
                            <td>₹${value.toFixed(2)}</td>
                            <td class="${pnlClass}">₹${pnl.toFixed(2)}</td>
                            <td class="${pnlClass}">${ret}%</td>
                        </tr>
                    `;
                });

                html += `</tbody></table>`;
                document.getElementById('holdings').innerHTML = html;
            } catch (error) {
                document.getElementById('holdings').innerHTML =
                    `<div class="empty">❌ Error: ${error.message}</div>`;
            }
        }

        // Load on page load
        window.addEventListener('load', loadHoldings);

        // Auto-refresh every 30 seconds
        setInterval(loadHoldings, 30000);
    </script>
</body>
</html>
'''

@app.route('/')
def index():
    return render_template_string(HTML)

@app.route('/api/holdings')
def get_holdings():
    try:
        if not client:
            return jsonify({"error": "5Paisa client not connected"}), 500

        holdings = client.holdings()

        if not holdings:
            return jsonify({"holdings": []})

        result = []
        for h in holdings:
            result.append({
                "symbol": h.get("symbol"),
                "quantity": int(h.get("quantity", 0)),
                "cost": float(h.get("cost", 0)),
                "ltp": float(h.get("ltp", 0))
            })

        return jsonify({"holdings": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    print("[START] 5Paisa Holdings Server")
    print("[URL] http://localhost:5000")
    app.run(host='127.0.0.1', port=5000, debug=False)

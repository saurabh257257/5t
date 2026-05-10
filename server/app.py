from flask import Flask, jsonify, render_template_string
from py5paisa import FivePaisaClient
import os
from dotenv import load_dotenv
import json
from datetime import datetime

load_dotenv()

app = Flask(__name__)

# 5Paisa Credentials
credentials = {
    "APP_NAME": os.getenv("APP_NAME", "5P58004979"),
    "APP_SOURCE": os.getenv("APP_SOURCE", "24930"),
    "USER_ID": os.getenv("USER_ID", "47xt4VnND2x"),
    "PASSWORD": os.getenv("PASSWORD", "B356hBPBrAK"),
    "USER_KEY": os.getenv("USER_KEY", "PyA72PuyUjYUiNavyRlN0bdLnc7aFeKp"),
    "ENCRYPTION_KEY": os.getenv("ENCRYPTION_KEY", "wnzELKnWbdH3KYdgAyW0EwLdVpnk2O1D")
}

# Initialize 5Paisa Client
try:
    client = FivePaisaClient(cred=credentials)
    print("✅ 5Paisa client connected")
except Exception as e:
    print(f"❌ 5Paisa connection error: {e}")
    client = None

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>5T Trading Bot - Holdings</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container {
            max-width: 1400px;
            margin: 0 auto;
        }
        header {
            color: white;
            text-align: center;
            margin-bottom: 30px;
        }
        header h1 { font-size: 2.5em; margin-bottom: 10px; }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 30px;
        }
        .stat-card {
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
        }
        .stat-label { font-size: 0.9em; color: #666; text-transform: uppercase; margin-bottom: 10px; }
        .stat-value { font-size: 2em; font-weight: bold; color: #333; }
        .stat-value.profit { color: #10b981; }
        .stat-value.loss { color: #ef4444; }

        .section {
            background: white;
            border-radius: 10px;
            padding: 25px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            margin-bottom: 30px;
        }
        .section-title {
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
            margin-bottom: 20px;
        }
        table thead {
            background: #f9fafb;
            border-bottom: 2px solid #e5e7eb;
        }
        table th {
            padding: 15px;
            text-align: left;
            font-weight: bold;
            color: #333;
            text-transform: uppercase;
            font-size: 0.85em;
        }
        table td {
            padding: 15px;
            border-bottom: 1px solid #e5e7eb;
            color: #666;
        }
        table tr:hover { background: #f9fafb; }

        .status-open { background: #dbeafe; color: #0c4a6e; padding: 5px 10px; border-radius: 20px; font-size: 0.85em; font-weight: bold; }
        .status-closed { background: #f0fdf4; color: #166534; padding: 5px 10px; border-radius: 20px; font-size: 0.85em; font-weight: bold; }

        .pnl-positive { color: #10b981; font-weight: bold; }
        .pnl-negative { color: #ef4444; font-weight: bold; }

        .empty-state {
            text-align: center;
            padding: 40px;
            color: #999;
        }
        .empty-icon { font-size: 3em; margin-bottom: 10px; }

        .loading {
            text-align: center;
            padding: 20px;
            color: #667eea;
        }
        .spinner {
            border: 4px solid #f3f4f6;
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
            transition: background 0.3s;
        }
        button:hover { background: #5568d3; }

        @media (max-width: 768px) {
            header h1 { font-size: 1.8em; }
            .stats-grid { grid-template-columns: 1fr; }
            table { font-size: 0.9em; }
            table th, table td { padding: 10px 5px; }
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>💼 5T Trading Bot</h1>
            <p>Holdings & Trading Dashboard</p>
        </header>

        <!-- Stats -->
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-label">Total Holdings</div>
                <div class="stat-value" id="totalHoldings">0</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Total P&L</div>
                <div class="stat-value" id="totalPnl">₹0</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Portfolio Value</div>
                <div class="stat-value" id="portfolioValue">₹0</div>
            </div>
        </div>

        <!-- Holdings -->
        <div class="section">
            <div class="section-title">📊 Current Holdings</div>
            <button onclick="loadHoldings()">🔄 Refresh</button>
            <div id="holdingsContainer" style="margin-top: 20px;">
                <div class="loading">
                    <div class="spinner"></div>
                    Loading holdings...
                </div>
            </div>
        </div>
    </div>

    <script>
        const API_BASE = window.location.origin;

        window.addEventListener('load', () => {
            loadHoldings();
            setInterval(loadHoldings, 30000); // Refresh every 30 seconds
        });

        async function loadHoldings() {
            try {
                const response = await fetch(`${API_BASE}/api/holdings`);
                const data = await response.json();

                if (data.success) {
                    renderHoldings(data.holdings || []);
                    updateStats(data.holdings || []);
                } else {
                    document.getElementById('holdingsContainer').innerHTML =
                        `<div class="empty-state"><div class="empty-icon">⚠️</div><p>${data.error || 'Error loading holdings'}</p></div>`;
                }
            } catch (error) {
                document.getElementById('holdingsContainer').innerHTML =
                    `<div class="empty-state"><div class="empty-icon">❌</div><p>Error: ${error.message}</p></div>`;
            }
        }

        function updateStats(holdings) {
            const totalHoldings = holdings.length;
            const totalValue = holdings.reduce((sum, h) => sum + (h.ltp * h.quantity), 0);
            const totalCost = holdings.reduce((sum, h) => sum + (h.cost * h.quantity), 0);
            const totalPnl = totalValue - totalCost;

            document.getElementById('totalHoldings').textContent = totalHoldings;
            document.getElementById('portfolioValue').textContent = `₹${totalValue.toFixed(2)}`;

            const pnlElement = document.getElementById('totalPnl');
            pnlElement.textContent = `₹${totalPnl.toFixed(2)}`;
            pnlElement.className = 'stat-value ' + (totalPnl >= 0 ? 'profit' : 'loss');
        }

        function renderHoldings(holdings) {
            const container = document.getElementById('holdingsContainer');

            if (!holdings || holdings.length === 0) {
                container.innerHTML = `
                    <div class="empty-state">
                        <div class="empty-icon">📭</div>
                        <p>No holdings found</p>
                    </div>
                `;
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
                            <th>Total Cost</th>
                            <th>Current Value</th>
                            <th>P&L</th>
                            <th>Return %</th>
                        </tr>
                    </thead>
                    <tbody>
            `;

            holdings.forEach(h => {
                const cost = h.cost * h.quantity;
                const value = h.ltp * h.quantity;
                const pnl = value - cost;
                const returnPct = ((pnl / cost) * 100).toFixed(2);
                const pnlClass = pnl >= 0 ? 'pnl-positive' : 'pnl-negative';

                html += `
                    <tr>
                        <td><strong>${h.symbol}</strong></td>
                        <td>${h.quantity}</td>
                        <td>₹${h.cost.toFixed(2)}</td>
                        <td>₹${h.ltp.toFixed(2)}</td>
                        <td>₹${cost.toFixed(2)}</td>
                        <td>₹${value.toFixed(2)}</td>
                        <td><span class="${pnlClass}">₹${pnl.toFixed(2)}</span></td>
                        <td><span class="${pnlClass}">${pnl >= 0 ? '+' : ''}${returnPct}%</span></td>
                    </tr>
                `;
            });

            html += `</tbody></table>`;
            container.innerHTML = html;
        }
    </script>
</body>
</html>
'''

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/holdings')
def get_holdings():
    try:
        if not client:
            return jsonify({
                "success": False,
                "error": "5Paisa client not connected"
            })

        # Get holdings from 5paisa
        holdings_data = client.get_holdings()

        if not holdings_data:
            return jsonify({
                "success": True,
                "holdings": []
            })

        holdings = []
        for holding in holdings_data:
            holdings.append({
                "symbol": holding.get("symbol", "N/A"),
                "quantity": holding.get("quantity", 0),
                "cost": float(holding.get("cost", 0)),
                "ltp": float(holding.get("ltp", 0)),  # Last Traded Price
            })

        return jsonify({
            "success": True,
            "holdings": holdings
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/status')
def status():
    return jsonify({
        "status": "running",
        "timestamp": datetime.now().isoformat(),
        "client_connected": client is not None
    })

if __name__ == '__main__':
    print("🚀 5T Trading Bot Server")
    print("📊 Starting on http://0.0.0.0:3000")
    print("")
    print("Dashboard: http://localhost:3000")
    app.run(host='0.0.0.0', port=3000, debug=False)

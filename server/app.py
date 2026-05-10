from flask import Flask, jsonify, request, send_from_directory
from py5paisa import FivePaisaClient
import os
from dotenv import load_dotenv
import sqlite3
from datetime import datetime
import threading
import time
import requests
import json

load_dotenv()

app = Flask(__name__, static_folder='public', static_url_path='')

# 5Paisa Credentials
cred = {
    "APP_NAME": os.getenv("APP_NAME", "5P58004979"),
    "APP_SOURCE": os.getenv("APP_SOURCE", "24930"),
    "USER_ID": os.getenv("USER_ID", "47xt4VnND2x"),
    "PASSWORD": os.getenv("PASSWORD", "B356hBPBrAK"),
    "USER_KEY": os.getenv("USER_KEY", "PyA72PuyUjYUiNavyRlN0bdLnc7aFeKp"),
    "ENCRYPTION_KEY": os.getenv("ENCRYPTION_KEY", "wnzELKnWbdH3KYdgAyW0EwLdVpnk2O1D")
}

# Initialize 5Paisa Client
try:
    client = FivePaisaClient(cred=cred)
    print("✅ 5Paisa client connected successfully")
except Exception as e:
    print(f"❌ 5Paisa connection error: {e}")
    client = None

# Database setup
def init_db():
    conn = sqlite3.connect('trading.db')
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY,
        timestamp DATETIME,
        type TEXT,
        symbol TEXT,
        strike_price REAL,
        entry_price REAL,
        exit_price REAL,
        quantity INTEGER,
        profit_loss REAL,
        status TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS settings (
        id INTEGER PRIMARY KEY,
        support REAL,
        resistance REAL,
        lot_size INTEGER,
        auth_key TEXT,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')

    conn.commit()
    conn.close()

init_db()

# Trading State
trading_state = {
    "isRunning": False,
    "currentPrice": 0,
    "support": 0,
    "resistance": 0,
    "lotSize": 0,
    "activeTrades": [],
    "lastSupportTouch": None,
    "lastResistanceTouchTime": None
}

# Fetch Sensex Price
def fetch_sensex_price():
    try:
        # Try NSE API
        response = requests.get(
            'https://www.nseindia.com/api/quote-equity?symbol=SENSEX',
            headers={'User-Agent': 'Mozilla/5.0'},
            timeout=5
        )
        if response.status_code == 200:
            data = response.json()
            if 'priceInfo' in data:
                return data['priceInfo']['lastPrice']
    except:
        pass

    try:
        # Fallback: Yahoo Finance
        response = requests.get(
            'https://query1.finance.yahoo.com/v8/finance/chart/%5EBSESN?interval=1m',
            timeout=5
        )
        if response.status_code == 200:
            data = response.json()
            return data['chart']['result'][0]['meta']['regularMarketPrice']
    except:
        pass

    return trading_state['currentPrice']

# Calculate strike price
def calculate_strike_price(current_price, trade_type):
    points = 1000
    slot = 100

    if trade_type == 'CALL':
        return int((current_price - points) / slot) * slot
    else:
        return int((current_price + points) / slot) * slot

# Get database connection
def get_db():
    conn = sqlite3.connect('trading.db')
    conn.row_factory = sqlite3.Row
    return conn

# Serve static files
@app.route('/')
def serve_index():
    return send_from_directory('public', 'index.html')

@app.route('/holdings.html')
def serve_holdings():
    return send_from_directory('public', 'holdings.html')

# API Endpoints
@app.route('/api/status', methods=['GET'])
def get_status():
    trading_state['currentPrice'] = fetch_sensex_price()

    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM settings ORDER BY id DESC LIMIT 1')
    settings = c.fetchone()
    conn.close()

    if settings:
        trading_state['support'] = settings['support']
        trading_state['resistance'] = settings['resistance']
        trading_state['lotSize'] = settings['lot_size']

    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT COUNT(*) as count FROM trades WHERE status = "open"')
    active = c.fetchone()
    conn.close()

    trading_state['activeTrades'] = active['count'] if active else 0

    return jsonify({
        "status": "running" if trading_state['isRunning'] else "stopped",
        "sensex": trading_state['currentPrice'],
        "support": trading_state['support'],
        "resistance": trading_state['resistance'],
        "lotSize": trading_state['lotSize'],
        "activeTrades": trading_state['activeTrades']
    })

@app.route('/api/settings', methods=['POST'])
def update_settings():
    data = request.json

    conn = sqlite3.connect('trading.db')
    c = conn.cursor()
    c.execute('''INSERT INTO settings (support, resistance, lot_size, auth_key, updated_at)
                 VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)''',
              (data.get('support'), data.get('resistance'), data.get('lotSize'), 'daily_key'))
    conn.commit()
    conn.close()

    trading_state['support'] = data.get('support')
    trading_state['resistance'] = data.get('resistance')
    trading_state['lotSize'] = data.get('lotSize')

    return jsonify({"message": "Settings updated"}), 200

@app.route('/api/start', methods=['POST'])
def start_trading():
    trading_state['isRunning'] = True
    print("🤖 Trading started")
    return jsonify({"message": "Trading started"}), 200

@app.route('/api/stop', methods=['POST'])
def stop_trading():
    trading_state['isRunning'] = False
    print("⏹️ Trading stopped")
    return jsonify({"message": "Trading stopped"}), 200

@app.route('/api/trades', methods=['GET'])
def get_trades():
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM trades ORDER BY created_at DESC LIMIT 100')
    trades = [dict(row) for row in c.fetchall()]
    conn.close()

    return jsonify(trades), 200

@app.route('/api/trades', methods=['POST'])
def create_trade():
    data = request.json

    conn = sqlite3.connect('trading.db')
    c = conn.cursor()
    c.execute('''INSERT INTO trades (timestamp, type, symbol, strike_price, entry_price,
                                     quantity, profit_loss, status, created_at)
                 VALUES (CURRENT_TIMESTAMP, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)''',
              (data['type'], data['symbol'], data['strike_price'], data['entry_price'],
               data['quantity'], data.get('profit_loss', 0), 'open'))
    conn.commit()
    conn.close()

    return jsonify({"message": "Trade created"}), 201

# Trading Bot Logic
def trading_bot():
    """Main trading bot loop"""
    print("🤖 Trading bot started")

    while True:
        try:
            if not trading_state['isRunning']:
                time.sleep(5)
                continue

            # Fetch current price
            current_price = fetch_sensex_price()
            trading_state['currentPrice'] = current_price

            # Get settings
            conn = get_db()
            c = conn.cursor()
            c.execute('SELECT * FROM settings ORDER BY id DESC LIMIT 1')
            settings = c.fetchone()
            conn.close()

            if not settings:
                time.sleep(5)
                continue

            support = settings['support']
            resistance = settings['resistance']
            lot_size = settings['lot_size']

            # Check support touch
            if current_price <= support and not trading_state['lastSupportTouch']:
                print(f"📍 Support touched: {current_price}")
                trading_state['lastSupportTouch'] = datetime.now()

                # Wait 5 minutes for confirmation
                time.sleep(300)

                # Check if price stayed below
                new_price = fetch_sensex_price()
                if new_price <= support:
                    strike = calculate_strike_price(new_price, 'CALL')
                    print(f"✅ CALL trade: Strike={strike}, Entry={new_price}")

                    # Create trade
                    conn = sqlite3.connect('trading.db')
                    c = conn.cursor()
                    c.execute('''INSERT INTO trades (timestamp, type, symbol, strike_price,
                                                     entry_price, quantity, status, created_at)
                                 VALUES (CURRENT_TIMESTAMP, ?, 'SENSEX', ?, ?, ?, 'open', CURRENT_TIMESTAMP)''',
                              ('CALL', strike, new_price, lot_size))
                    conn.commit()
                    conn.close()

            # Check resistance touch
            if current_price >= resistance and not trading_state['lastResistanceTouchTime']:
                print(f"📍 Resistance touched: {current_price}")
                trading_state['lastResistanceTouchTime'] = datetime.now()

                # Wait 5 minutes for confirmation
                time.sleep(300)

                # Check if price stayed above
                new_price = fetch_sensex_price()
                if new_price >= resistance:
                    strike = calculate_strike_price(new_price, 'PUT')
                    print(f"✅ PUT trade: Strike={strike}, Entry={new_price}")

                    # Create trade
                    conn = sqlite3.connect('trading.db')
                    c = conn.cursor()
                    c.execute('''INSERT INTO trades (timestamp, type, symbol, strike_price,
                                                     entry_price, quantity, status, created_at)
                                 VALUES (CURRENT_TIMESTAMP, ?, 'SENSEX', ?, ?, ?, 'open', CURRENT_TIMESTAMP)''',
                              ('PUT', strike, new_price, lot_size))
                    conn.commit()
                    conn.close()

            # Reset touches if price moved away
            if current_price > support + 100:
                trading_state['lastSupportTouch'] = None
            if current_price < resistance - 100:
                trading_state['lastResistanceTouchTime'] = None

            time.sleep(30)

        except Exception as e:
            print(f"❌ Bot error: {e}")
            time.sleep(10)

# Start bot in background thread
bot_thread = threading.Thread(target=trading_bot, daemon=True)
bot_thread.start()

if __name__ == '__main__':
    print("🚀 5T Trading Bot Server")
    print(f"📊 Starting on http://0.0.0.0:3000")
    app.run(host='0.0.0.0', port=3000, debug=False)

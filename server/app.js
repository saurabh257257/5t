const express = require('express');
const axios = require('axios');
require('dotenv').config();
const sqlite3 = require('sqlite3').verbose();
const http = require('http');
const socketIo = require('socket.io');

const app = express();
const server = http.createServer(app);
const io = socketIo(server, {
  cors: { origin: "*" }
});

app.use(express.json());
app.use(express.static('public'));

// Database setup
const db = new sqlite3.Database('./trading.db');

db.run(`
  CREATE TABLE IF NOT EXISTS trades (
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
  )
`);

db.run(`
  CREATE TABLE IF NOT EXISTS settings (
    id INTEGER PRIMARY KEY,
    support REAL,
    resistance REAL,
    lot_size INTEGER,
    auth_key TEXT,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
  )
`);

// 5Paisa Credentials
const fivePaisaCredentials = {
  "APP_NAME": process.env.APP_NAME || "5P58004979",
  "APP_SOURCE": process.env.APP_SOURCE || "24930",
  "USER_ID": process.env.USER_ID || "47xt4VnND2x",
  "PASSWORD": process.env.PASSWORD || "B356hBPBrAK",
  "USER_KEY": process.env.USER_KEY || "PyA72PuyUjYUiNavyRlN0bdLnc7aFeKp",
  "ENCRYPTION_KEY": process.env.ENCRYPTION_KEY || "wnzELKnWbdH3KYdgAyW0EwLdVpnk2O1D"
};

// Trading State
let tradingState = {
  isRunning: false,
  currentPrice: 0,
  support: 0,
  resistance: 0,
  lotSize: 0,
  activeTrades: [],
  lastSupportTouch: null,
  lastResistanceTouchTime: null
};

// Fetch Sensex Price from NSE
async function fetchSensexPrice() {
  try {
    // Using NSE India API
    const response = await axios.get('https://www.nseindia.com/api/quote-equity?symbol=SENSEX', {
      headers: { 'User-Agent': 'Mozilla/5.0' }
    });

    if (response.data && response.data.priceInfo) {
      return response.data.priceInfo.lastPrice;
    }

    // Fallback: Try Yahoo Finance
    const fallback = await axios.get('https://query1.finance.yahoo.com/v8/finance/chart/%5EBSESN?interval=1m');
    const price = fallback.data.chart.result[0].meta.regularMarketPrice;
    return price;
  } catch (error) {
    console.error('Error fetching Sensex price:', error.message);
    return tradingState.currentPrice; // Return last known price
  }
}

// Calculate strike price (1000 points ITM in 100-point slots)
function calculateStrikePrice(currentPrice, type) {
  const points = 1000;
  const slot = 100;

  if (type === 'CALL') {
    // Call: 1000 points below current price
    return Math.floor((currentPrice - points) / slot) * slot;
  } else {
    // Put: 1000 points above current price
    return Math.ceil((currentPrice + points) / slot) * slot;
  }
}

// Check support/resistance logic
async function checkTradingSignals(currentPrice) {
  const support = tradingState.support;
  const resistance = tradingState.resistance;
  const now = Date.now();
  const fiveMinutes = 5 * 60 * 1000;

  // Support Hit Logic
  if (currentPrice <= support && !tradingState.lastSupportTouch) {
    tradingState.lastSupportTouch = now;
    console.log('🎯 Support touched! Monitoring for 5 minutes...');
  }

  if (tradingState.lastSupportTouch && (now - tradingState.lastSupportTouch) >= fiveMinutes) {
    if (currentPrice <= support + 50) { // Still at support
      console.log('✅ Support confirmed for 5 minutes!');

      // Determine if price is going up (buy CALL) or down (buy PUT)
      const shouldBuyCall = currentPrice > support; // Bouncing up
      const orderType = shouldBuyCall ? 'CALL' : 'PUT';

      await executeTrade(orderType, currentPrice);
      tradingState.lastSupportTouch = null;
    }
  }

  // Resistance Hit Logic
  if (currentPrice >= resistance && !tradingState.lastResistanceTouchTime) {
    tradingState.lastResistanceTouchTime = now;
    console.log('⚠️ Resistance touched! Monitoring movement...');
  }

  if (tradingState.lastResistanceTouchTime) {
    const timeSinceTouch = now - tradingState.lastResistanceTouchTime;

    // If stays below resistance for confirmation
    if (currentPrice < resistance && timeSinceTouch > 30000) { // 30 seconds
      console.log('📉 Resistance confirmed, price moving down - Buy PUT');
      await executeTrade('PUT', currentPrice);
      tradingState.lastResistanceTouchTime = null;
    }

    // If bounces up from resistance
    if (currentPrice > resistance && timeSinceTouch > 30000) {
      console.log('📈 Resistance bounced up - Buy CALL');
      await executeTrade('CALL', currentPrice);
      tradingState.lastResistanceTouchTime = null;
    }
  }
}

// Execute Trade
async function executeTrade(orderType, currentPrice) {
  try {
    const strikePrice = calculateStrikePrice(currentPrice, orderType);
    const quantity = tradingState.lotSize;

    console.log(`
      🚀 EXECUTING TRADE
      Type: ${orderType}
      Strike: ${strikePrice}
      Current Price: ${currentPrice}
      Quantity: ${quantity}
      SL: ${currentPrice - 150}
      TP: ${currentPrice + 450}
    `);

    // Create trade record
    db.run(
      `INSERT INTO trades (type, symbol, strike_price, entry_price, quantity, status, timestamp)
       VALUES (?, ?, ?, ?, ?, ?, datetime('now'))`,
      [orderType, 'SENSEX', strikePrice, currentPrice, quantity, 'ACTIVE']
    );

    tradingState.activeTrades.push({
      id: Date.now(),
      type: orderType,
      strikePrice: strikePrice,
      entryPrice: currentPrice,
      quantity: quantity,
      stopLoss: currentPrice - 150,
      profitTarget: currentPrice + 450,
      createdAt: new Date()
    });

    // Broadcast to connected clients
    io.emit('trade', {
      type: orderType,
      strikePrice: strikePrice,
      entryPrice: currentPrice,
      stopLoss: currentPrice - 150,
      profitTarget: currentPrice + 450,
      timestamp: new Date()
    });

  } catch (error) {
    console.error('Trade execution error:', error);
  }
}

// Monitor active trades for SL/TP
async function monitorActiveTrades(currentPrice) {
  const updatedTrades = [];

  for (let trade of tradingState.activeTrades) {
    let shouldClose = false;
    let closeReason = '';
    let exitPrice = currentPrice;

    // Check Stop Loss (150 points)
    if (Math.abs(currentPrice - trade.entryPrice) >= 150) {
      if (currentPrice < trade.entryPrice) { // Price went down
        shouldClose = true;
        closeReason = 'STOP_LOSS';
        exitPrice = trade.entryPrice - 150;
      }
    }

    // Check Profit Target (450 points)
    if (currentPrice > trade.entryPrice + 450) {
      shouldClose = true;
      closeReason = 'PROFIT_TARGET';
      exitPrice = trade.entryPrice + 450;
    }

    if (shouldClose) {
      const profitLoss = (exitPrice - trade.entryPrice) * trade.quantity;

      console.log(`
        ✅ TRADE CLOSED
        Reason: ${closeReason}
        P&L: ${profitLoss}
      `);

      // Update database
      db.run(
        `UPDATE trades SET exit_price = ?, profit_loss = ?, status = ? WHERE id = ?`,
        [exitPrice, profitLoss, 'CLOSED', trade.id]
      );

      // Broadcast closure
      io.emit('trade_closed', {
        tradeId: trade.id,
        reason: closeReason,
        exitPrice: exitPrice,
        profitLoss: profitLoss
      });
    } else {
      updatedTrades.push(trade);
    }
  }

  tradingState.activeTrades = updatedTrades;
}

// Main monitoring loop
async function startMonitoring() {
  if (!tradingState.isRunning) return;

  try {
    const currentPrice = await fetchSensexPrice();
    tradingState.currentPrice = currentPrice;

    console.log(`📊 Sensex: ${currentPrice}`);

    // Check trading signals
    await checkTradingSignals(currentPrice);

    // Monitor active trades
    await monitorActiveTrades(currentPrice);

    // Broadcast status
    io.emit('status', {
      sensex: currentPrice,
      support: tradingState.support,
      resistance: tradingState.resistance,
      activeTrades: tradingState.activeTrades.length,
      timestamp: new Date()
    });

  } catch (error) {
    console.error('Monitoring error:', error);
  }

  // Check every 5 seconds
  setTimeout(startMonitoring, 5000);
}

// API Endpoints

// Get current status
app.get('/api/status', (req, res) => {
  res.json({
    status: 'running',
    sensex: tradingState.currentPrice,
    support: tradingState.support,
    resistance: tradingState.resistance,
    lotSize: tradingState.lotSize,
    activeTrades: tradingState.activeTrades.length,
    timestamp: new Date()
  });
});

// Update settings
app.post('/api/settings', (req, res) => {
  const { support, resistance, lotSize, authKey } = req.body;

  tradingState.support = support;
  tradingState.resistance = resistance;
  tradingState.lotSize = lotSize;

  db.run(
    `INSERT INTO settings (support, resistance, lot_size, auth_key) VALUES (?, ?, ?, ?)
     ON CONFLICT(id) DO UPDATE SET support=?, resistance=?, lot_size=?, auth_key=?, updated_at=datetime('now')`,
    [support, resistance, lotSize, authKey, support, resistance, lotSize, authKey]
  );

  io.emit('settings_updated', { support, resistance, lotSize });

  res.json({ success: true, message: 'Settings updated' });
});

// Start trading
app.post('/api/start', (req, res) => {
  tradingState.isRunning = true;
  startMonitoring();
  io.emit('trading_started');
  res.json({ success: true, message: 'Trading started' });
});

// Stop trading
app.post('/api/stop', (req, res) => {
  tradingState.isRunning = false;
  io.emit('trading_stopped');
  res.json({ success: true, message: 'Trading stopped' });
});

// Get trade history
app.get('/api/trades', (req, res) => {
  db.all('SELECT * FROM trades ORDER BY created_at DESC LIMIT 100', [], (err, rows) => {
    if (err) {
      res.status(500).json({ error: err.message });
      return;
    }
    res.json(rows);
  });
});

// Socket.io connection
io.on('connection', (socket) => {
  console.log('📱 Client connected:', socket.id);

  socket.emit('status', {
    sensex: tradingState.currentPrice,
    support: tradingState.support,
    resistance: tradingState.resistance,
    activeTrades: tradingState.activeTrades
  });

  socket.on('disconnect', () => {
    console.log('📱 Client disconnected:', socket.id);
  });
});

// Start server
const PORT = process.env.PORT || 3000;
server.listen(PORT, () => {
  console.log(`
    ╔════════════════════════════════════╗
    ║   5T TRADING BOT - RUNNING 🤖    ║
    ║   Server: http://localhost:${PORT}     ║
    ║   Monitoring: SENSEX              ║
    ╚════════════════════════════════════╝
  `);
});

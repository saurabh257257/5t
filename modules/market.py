import re
from datetime import datetime, timezone, timedelta, date as _date

_IST = timezone(timedelta(hours=5, minutes=30))


def _market_open_now():
    """True only during NSE/BSE live trading hours (IST), Mon–Fri."""
    from datetime import time as _t
    now = datetime.now(_IST)
    if now.weekday() >= 5:          # Saturday=5, Sunday=6
        return False
    t = now.time()
    return _t(9, 14) <= t <= _t(15, 31)


def get_ltp(client, scripcode, exch="N", exch_type="C"):
    try:
        req = [{"Exch": exch, "ExchangeType": exch_type, "ScripCode": int(scripcode)}]
        result = client.fetch_market_feed(req)
        if not result:
            return {"error": "No data returned"}
        item = result[0] if isinstance(result, list) else result
        return {
            "ltp":        float(item.get("LastRate") or item.get("LTP") or 0),
            "change":     float(item.get("Change") or 0),
            "change_pct": float(item.get("PercentChange") or 0),
            "open":       float(item.get("OpenRate") or item.get("Open") or 0),
            "high":       float(item.get("High") or item.get("HighRate") or 0),
            "low":        float(item.get("Low") or item.get("LowRate") or 0),
            "close":      float(item.get("CloseRate") or item.get("PreviousClose") or 0),
            "volume":     int(item.get("Volume") or item.get("TotalQty") or 0),
        }
    except Exception as e:
        return {"error": str(e)}


def _fetch_hist_close(client, exch, scrip_code, days=10):
    """Fetch last N days of daily candles. Returns list of closes, most recent last."""
    from datetime import timedelta
    today     = _date.today().strftime('%Y-%m-%d')
    from_date = (_date.today() - timedelta(days=days)).strftime('%Y-%m-%d')
    for et in ('C', 'D'):   # try Cash first, then Derivatives
        try:
            df = client.historical_data(exch, et, int(scrip_code), '1d', from_date, today)
            if df is not None and len(df) > 0:
                closes = []
                for _, row in df.iterrows():
                    c = float(row.get('Close') or row.get('close') or 0)
                    if c > 0:
                        closes.append(c)
                if closes:
                    return closes
        except Exception:
            continue
    return []


def get_index_ltp(client, exch, scrip_code, opt_symbol=None, chart_scrip=None):
    """
    Generic index LTP with proper prev-close and change calculation.
    prev_close priority: (1) CloseRate/PreviousClose from live feed,
    (2) last historical daily close (chart_scrip used for NIFTY etc).
    """
    # ── 1. Try live market feed ───────────────────────────────────────────────
    ltp = prev_close_feed = open_ = high = low = 0
    market_open = _market_open_now()   # time-based, not feed-based
    try:
        req = [{"Exch": exch, "ExchangeType": "C", "ScripCode": int(scrip_code)}]
        result = client.fetch_market_feed(req)
        if result:
            item = result[0] if isinstance(result, list) else result
            ltp             = float(item.get("LastRate")      or item.get("LTP")           or 0)
            prev_close_feed = float(item.get("PreviousClose") or item.get("CloseRate")     or 0)
            open_           = float(item.get("OpenRate")      or item.get("Open")          or 0)
            high            = float(item.get("High")          or item.get("HighRate")      or 0)
            low             = float(item.get("Low")           or item.get("LowRate")       or 0)
    except Exception:
        pass

    # ── 2. Fallback: get LTP from expiry API (always works for any index) ─────
    if ltp == 0 and opt_symbol:
        try:
            result = client.get_expiry(exch, opt_symbol)
            if result:
                last_rate = result.get("lastrate", [{}])
                ltp = float(last_rate[0].get("LTP", 0)) if last_rate else 0
                market_open = ltp > 0
        except Exception:
            pass

    # ── 3. prev_close — use feed value if available, else historical ──────────
    # Feed's CloseRate/PreviousClose is the exchange-reported previous-day close.
    # When feed returns it, it's always correct regardless of market state.
    if prev_close_feed > 0:
        prev_close = prev_close_feed
    else:
        # Fallback: historical daily closes (chart_scrip e.g. 999920000 for NIFTY)
        h_scrip = chart_scrip if chart_scrip else scrip_code
        closes  = _fetch_hist_close(client, exch, h_scrip, days=25)
        if closes:
            if ltp == 0:
                ltp = closes[-1]            # use last close as price when feed is empty
            # When market is open: last hist candle = yesterday = prev_close
            # When market is closed: last hist candle = today/last-trading-day,
            #   so prev_close = the one before it
            prev_close = closes[-1] if market_open else (
                closes[-2] if len(closes) >= 2 else closes[-1]
            )
        else:
            prev_close = 0

    # ── 4. Compute change vs prev_close ──────────────────────────────────────
    if prev_close > 0 and ltp > 0:
        change     = round(ltp - prev_close, 2)
        change_pct = round((change / prev_close) * 100, 2)
    else:
        change = change_pct = 0

    return {
        "ltp":         ltp,
        "prev_close":  prev_close,
        "change":      change,
        "change_pct":  change_pct,
        "open":        open_,
        "high":        high,
        "low":         low,
        "market_open": market_open,
    }


def get_sensex_ltp(client):
    return get_index_ltp(client, 'B', 999901, 'SENSEX')


def get_expiry_dates(client, exch, symbol):
    try:
        result = client.get_expiry(exch, symbol)
        if not result:
            return {"expiries": [], "ltp": 0}
        expiries_raw = result.get("Expiry", [])
        last_rate    = result.get("lastrate", [{}])
        ltp = float(last_rate[0].get("LTP", 0)) if last_rate else 0
        expiries = []
        for item in expiries_raw:
            match = re.search(r'\d+', item.get("ExpiryDate", ""))
            if match:
                ms = int(match.group())
                dt = datetime.fromtimestamp(ms / 1000, tz=_IST)
                expiries.append({"label": dt.strftime("%d %b %Y (%A)"), "ts": ms})
        return {"expiries": expiries, "ltp": ltp}
    except Exception as e:
        return {"error": str(e)}


def get_option_chain_data(client, exch, symbol, expiry_ts):
    try:
        result = client.get_option_chain(exch, symbol, int(expiry_ts))
        if not result:
            return {"option_chain": []}
        options = result.get("Options", [])
        ce_map, pe_map = {}, {}
        for item in options:
            strike = float(item.get("StrikeRate", 0))
            entry  = {
                "scrip":   int(item.get("ScripCode", 0)),
                "ltp":     float(item.get("LastRate", 0)),
                "oi":      int(item.get("OpenInterest", 0)),
                "chg_oi":  int(item.get("ChangeInOI", 0)),
                "vol":     int(item.get("Volume", 0)),
            }
            if item.get("CPType") == "CE":
                ce_map[strike] = entry
            elif item.get("CPType") == "PE":
                pe_map[strike] = entry
        rows = []
        for s in sorted(set(ce_map) | set(pe_map)):
            ce = ce_map.get(s, {})
            pe = pe_map.get(s, {})
            rows.append({
                "strike":    s,
                "ce_scrip":  ce.get("scrip", 0),
                "ce_ltp":    ce.get("ltp", 0),
                "ce_oi":     ce.get("oi", 0),
                "ce_chg_oi": ce.get("chg_oi", 0),
                "ce_vol":    ce.get("vol", 0),
                "pe_scrip":  pe.get("scrip", 0),
                "pe_ltp":    pe.get("ltp", 0),
                "pe_oi":     pe.get("oi", 0),
                "pe_chg_oi": pe.get("chg_oi", 0),
                "pe_vol":    pe.get("vol", 0),
            })
        return {"option_chain": rows}
    except Exception as e:
        return {"error": str(e)}


def get_historical_data(client, exch, exch_type, scrip_code, interval="15m", days=2):
    try:
        from datetime import timedelta
        today      = _date.today().strftime('%Y-%m-%d')
        from_date  = (_date.today() - timedelta(days=int(days) - 1)).strftime('%Y-%m-%d')
        df = client.historical_data(exch, exch_type, int(scrip_code), interval, from_date, today)
        if df is None:
            return {"error": "No data returned"}
        return {"candles": df.to_dict(orient='records')}
    except Exception as e:
        return {"error": str(e)}


def get_today_ohlc(client, exch, scrip_code):
    """
    Fetch Open/High/Low for the current (or most recent) trading day.
    1. Tries today's 15m intraday candles (works when market is open).
    2. Falls back to most recent daily candle (works when market is closed/holiday).
    Returns {open, high, low} or {error}.
    """
    from datetime import timedelta as _td2
    today     = _date.today().strftime('%Y-%m-%d')
    past_week = (_date.today() - _td2(days=7)).strftime('%Y-%m-%d')

    # ── 1. Try intraday 15m (market open) ────────────────────────────────────
    for et in ('C', 'D'):
        try:
            df = client.historical_data(exch, et, int(scrip_code), '15m', today, today)
            if df is None or len(df) == 0:
                continue
            opens = [float(r.get('Open') or r.get('open') or 0) for _, r in df.iterrows()]
            highs = [float(r.get('High') or r.get('high') or 0) for _, r in df.iterrows()]
            lows  = [float(r.get('Low')  or r.get('low')  or 0) for _, r in df.iterrows()]
            opens = [v for v in opens if v > 0]
            highs = [v for v in highs if v > 0]
            lows  = [v for v in lows  if v > 0]
            if opens and highs and lows:
                return {'open': opens[0], 'high': max(highs), 'low': min(lows)}
        except Exception:
            continue

    # ── 2. Fallback: most recent daily candle (market closed / holiday) ───────
    for et in ('C', 'D'):
        try:
            df = client.historical_data(exch, et, int(scrip_code), '1d', past_week, today)
            if df is None or len(df) == 0:
                continue
            row = df.iloc[-1]
            o = float(row.get('Open') or row.get('open') or 0)
            h = float(row.get('High') or row.get('high') or 0)
            l = float(row.get('Low')  or row.get('low')  or 0)
            if o > 0:
                return {'open': o, 'high': h, 'low': l}
        except Exception:
            continue

    return {'error': 'No OHLC data available'}


def get_chart_data(client, exch, scrip_code, interval='4h', days=365):
    """
    Fetch OHLCV candles for charting (TradingView lightweight-charts format).
    Falls back: 4h → 1h → 1d.
    Returns {candles:[{time(unix_sec), open, high, low, close, volume}], interval_used, count}
    """
    from datetime import timedelta as _td, datetime as _dt
    # Use last trading day as to_date (skip weekends)
    last_trading = _date.today()
    while last_trading.weekday() >= 5:   # 5=Sat, 6=Sun
        last_trading -= _td(days=1)
    today     = last_trading.strftime('%Y-%m-%d')
    from_date = (last_trading - _td(days=days)).strftime('%Y-%m-%d')

    # 5paisa valid intervals: 1m,5m,10m,15m,30m,60m,1d (lowercase)
    fallbacks = {'4h': ['60m', '1d'], '1h': ['60m', '1d'], '1d': ['1d']}
    ivl_list  = fallbacks.get(interval, ['60m', '1d'])

    for ivl in ivl_list:
        for et in ('C', 'D'):
            try:
                df = client.historical_data(exch, et, int(scrip_code), ivl, from_date, today)
                if df is None or isinstance(df, str) or len(df) < 5:
                    continue
                candles = []
                for _, row in df.iterrows():
                    dt_val = row.get('Datetime') or row.get('datetime') or ''
                    try:
                        # Handle pandas Timestamp or string
                        s = str(dt_val)[:19].replace('T', ' ')
                        dt = _dt.strptime(s, '%Y-%m-%d %H:%M:%S')
                        # Convert IST naive datetime to UTC unix seconds
                        unix_ts = int((dt - _dt(1970, 1, 1) - _td(hours=5, minutes=30)).total_seconds())
                    except Exception:
                        continue
                    o = float(row.get('Open')   or row.get('open')   or 0)
                    h = float(row.get('High')   or row.get('high')   or 0)
                    l = float(row.get('Low')    or row.get('low')    or 0)
                    c = float(row.get('Close')  or row.get('close')  or 0)
                    v = int(  row.get('Volume') or row.get('volume') or 0)
                    if o > 0 and c > 0:
                        candles.append({'time': unix_ts, 'open': o, 'high': h,
                                        'low': l, 'close': c, 'volume': v})
                if len(candles) >= 5:
                    return {'candles': candles, 'interval_used': ivl, 'count': len(candles)}
            except Exception:
                continue

    return {'error': 'No chart data available for any interval', 'candles': []}


def _extract_ltp(item):
    """Extract best available price from a market feed item."""
    for field in ('LastRate', 'LTP', 'Last', 'CloseRate', 'PreviousClose', 'Close'):
        v = item.get(field)
        if v:
            try:
                f = float(v)
                if f > 0:
                    return f
            except Exception:
                pass
    return 0.0


def get_components_ltp(client, components, exch, exch_type):
    """
    Batch-fetch LTPs for component stocks.
    Splits into batches of 25 (API safe limit).
    Returns {components: [...]} or {error}.
    """
    if not components:
        return {'error': 'No components provided'}

    BATCH = 25
    all_items = []

    for start in range(0, len(components), BATCH):
        batch = components[start:start + BATCH]
        req = [
            {'Exch': exch, 'ExchangeType': exch_type, 'ScripCode': int(c['scrip_code'])}
            for c in batch
        ]
        try:
            feed = client.fetch_market_feed(req)
            items = feed if isinstance(feed, list) else ([feed] if feed else [])
            # Pad with empty dicts if response is shorter than request
            while len(items) < len(batch):
                items.append({})
            all_items.extend(items[:len(batch)])
        except Exception:
            all_items.extend([{}] * len(batch))

    enriched = []
    for i, comp in enumerate(components):
        item    = all_items[i] if i < len(all_items) else {}
        ltp     = _extract_ltp(item)
        change  = float(item.get('Change')        or 0)
        chg_pct = float(item.get('PercentChange') or 0)
        weight  = float(comp.get('weight', 0))
        contrib = round(weight * chg_pct / 100, 4)
        enriched.append({
            'rank':         comp['rank'],
            'name':         comp['name'],
            'sector':       comp['sector'],
            'scrip_code':   comp['scrip_code'],
            'weight':       weight,
            'ltp':          ltp,
            'change':       round(change, 2),
            'change_pct':   round(chg_pct, 2),
            'contribution': contrib,
        })

    enriched.sort(key=lambda x: abs(x['contribution']), reverse=True)
    return {'components': enriched}

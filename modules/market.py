import re
from datetime import datetime, timezone, timedelta, date as _date

_IST = timezone(timedelta(hours=5, minutes=30))


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


def get_index_ltp(client, exch, scrip_code):
    """Generic index LTP — works for SENSEX (B/999901), NIFTY (N/999920), BANKNIFTY (N/999921)."""
    try:
        req = [{"Exch": exch, "ExchangeType": "C", "ScripCode": int(scrip_code)}]
        result = client.fetch_market_feed(req)
        if not result:
            return {"error": "No data"}
        item = result[0] if isinstance(result, list) else result
        ltp = (float(item.get("LastRate") or 0) or
               float(item.get("LTP") or 0) or
               float(item.get("CloseRate") or 0) or
               float(item.get("PreviousClose") or 0))
        prev_close = float(item.get("CloseRate") or item.get("PreviousClose") or 0)

        # If everything is 0 (pre-market / weekend) fetch last close from history
        if ltp == 0:
            try:
                from datetime import timedelta
                today     = _date.today().strftime('%Y-%m-%d')
                from_date = (_date.today() - timedelta(days=7)).strftime('%Y-%m-%d')
                df = client.historical_data(exch, 'C', int(scrip_code), '1d', from_date, today)
                if df is not None and len(df) > 0:
                    last_row   = df.iloc[-1]
                    ltp        = float(last_row.get('Close', 0) or last_row.get('close', 0))
                    prev_close = ltp
            except Exception:
                pass

        return {
            "ltp":         ltp,
            "change":      float(item.get("Change") or 0),
            "change_pct":  float(item.get("PercentChange") or 0),
            "open":        float(item.get("OpenRate") or item.get("Open") or 0),
            "high":        float(item.get("High") or item.get("HighRate") or 0),
            "low":         float(item.get("Low") or item.get("LowRate") or 0),
            "close":       prev_close,
            "market_open": float(item.get("LastRate") or 0) > 0,
        }
    except Exception as e:
        return {"error": str(e)}


def get_sensex_ltp(client):
    return get_index_ltp(client, 'B', 999901)


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

from datetime import datetime


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


def get_expiry_dates(client, exch, symbol):
    try:
        result = client.get_expiry(exch, symbol)
        if not result:
            return {"expiries": []}
        expiries = result if isinstance(result, list) else result.get("Expiry", [])
        return {"expiries": expiries}
    except Exception as e:
        return {"error": str(e)}


def get_option_chain_data(client, exch, symbol, expiry_str):
    try:
        dt = datetime.strptime(expiry_str, "%Y-%m-%d")
        expiry_ts = int(dt.timestamp() * 1000)
        result = client.get_option_chain(exch, symbol, expiry_ts)
        if not result:
            return {"option_chain": []}
        chain = result if isinstance(result, list) else result.get("Data", result.get("data", []))
        rows = []
        for item in chain:
            rows.append({
                "strike":     float(item.get("StrikeRate") or item.get("Strike") or 0),
                "ce_ltp":     float(item.get("CE_LTP") or item.get("CallLTP") or 0),
                "ce_oi":      int(item.get("CE_OI") or item.get("CallOI") or 0),
                "ce_volume":  int(item.get("CE_Volume") or item.get("CallVolume") or 0),
                "ce_change":  float(item.get("CE_Change") or 0),
                "pe_ltp":     float(item.get("PE_LTP") or item.get("PutLTP") or 0),
                "pe_oi":      int(item.get("PE_OI") or item.get("PutOI") or 0),
                "pe_volume":  int(item.get("PE_Volume") or item.get("PutVolume") or 0),
                "pe_change":  float(item.get("PE_Change") or 0),
            })
        return {"option_chain": rows, "raw": chain[:2] if chain else []}
    except Exception as e:
        return {"error": str(e)}

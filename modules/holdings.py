def get_holdings_data(client):
    try:
        data = client.holdings()
        if not data:
            return {"holdings": []}
        result = []
        for h in data:
            result.append({
                "symbol": h.get("Symbol") or h.get("symbol", "N/A"),
                "quantity": int(h.get("Quantity") or h.get("quantity") or 0),
                "cost": float(h.get("AvgRate") or h.get("cost") or 0),
                "ltp": float(h.get("LTP") or h.get("ltp") or 0),
            })
        return {"holdings": result}
    except Exception as e:
        return {"error": str(e)}

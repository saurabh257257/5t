"""
debug_feeds.py  —  test live feed, chart OHLC, and prev-close for all indices
Run from project root:  python debug_feeds.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from modules.auth import try_restore_session, authenticated_clients

cid = try_restore_session()
client = authenticated_clients.get(cid) if cid else None
if not client:
    print("ERROR: not authenticated — log in via the web app first")
    sys.exit(1)

TESTS = [
    # exch  et    feed_scrip  chart_scrip   label
    ('N', 'C',  999920,    999920000,   'NIFTY'),
    ('N', 'C',  999921,    999920005,   'BANKNIFTY'),
    ('N', 'C',  999922,    999920041,   'FINNIFTY'),
    ('B', 'C',  999901,    999901,      'SENSEX'),
]

FROM_DATE = '2026-01-01'
TO_DATE   = '2026-05-16'

print("=" * 70)
print(f"{'INDEX':<12} {'TEST':<30} {'RESULT'}")
print("=" * 70)

for exch, et, feed_scrip, chart_scrip, label in TESTS:

    # ── 1. Live market feed ───────────────────────────────────────────────────
    try:
        req = [{"Exch": exch, "ExchangeType": et, "ScripCode": int(feed_scrip)}]
        r = client.fetch_market_feed(req)
        if r:
            item = r[0] if isinstance(r, list) else r
            ltp   = item.get("LastRate") or item.get("LTP")
            open_ = item.get("OpenRate") or item.get("Open")
            high  = item.get("High")     or item.get("HighRate")
            low   = item.get("Low")      or item.get("LowRate")
            prev  = item.get("PreviousClose") or item.get("CloseRate")
            print(f"{label:<12} {'live feed (feed_scrip)':<30} LTP={ltp}  O={open_}  H={high}  L={low}  PrevClose={prev}")
            print(f"{'':12} {'  raw keys':<30} {sorted(item.keys())}")
        else:
            print(f"{label:<12} {'live feed (feed_scrip)':<30} empty response")
    except Exception as e:
        print(f"{label:<12} {'live feed (feed_scrip)':<30} ERROR: {e}")

    # ── 2. Historical daily — feed_scrip ─────────────────────────────────────
    for scrip, tag in [(feed_scrip, 'hist 1d feed_scrip'), (chart_scrip, 'hist 1d chart_scrip')]:
        try:
            df = client.historical_data(exch, et, int(scrip), '1d', FROM_DATE, TO_DATE)
            if df is None or len(df) == 0:
                print(f"{label:<12} {tag:<30} empty")
            else:
                last = df.iloc[-1]
                print(f"{label:<12} {tag:<30} rows={len(df)}  cols={list(df.columns)}")
                print(f"{'':12} {'  last row':<30} {dict(last)}")
        except Exception as e:
            print(f"{label:<12} {tag:<30} ERROR: {e}")

    # ── 3. Historical 15m today — chart_scrip ────────────────────────────────
    from datetime import date
    today = date.today().strftime('%Y-%m-%d')
    try:
        df = client.historical_data(exch, et, int(chart_scrip), '15m', today, today)
        if df is None or len(df) == 0:
            print(f"{label:<12} {'hist 15m today':<30} empty")
        else:
            last = df.iloc[-1]
            print(f"{label:<12} {'hist 15m today':<30} rows={len(df)}  last={dict(last)}")
    except Exception as e:
        print(f"{label:<12} {'hist 15m today':<30} ERROR: {e}")

    print("-" * 70)

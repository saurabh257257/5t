"""
debug_feeds.py  —  test live feed, chart OHLC, and prev-close for all indices
Run from project root:  python debug_feeds.py
"""
import sys, os, threading
sys.path.insert(0, os.path.dirname(__file__))

from modules.auth import try_restore_session, authenticated_clients

cid = try_restore_session()
client = authenticated_clients.get(cid) if cid else None
if not client:
    print("ERROR: not authenticated — log in via the web app first")
    sys.exit(1)

print("Authenticated OK\n")

TESTS = [
    # exch  et    feed_scrip  chart_scrip   label
    ('N', 'C',  999920,    999920000,   'NIFTY'),
    ('N', 'C',  999921,    999920005,   'BANKNIFTY'),
    ('N', 'C',  999922,    999920041,   'FINNIFTY'),
    ('B', 'C',  999901,    999901,      'SENSEX'),
]

FROM_DATE = '2026-01-01'
TO_DATE   = '2026-05-19'

def run_with_timeout(fn, timeout=8):
    result = [None]
    err    = [None]
    def _run():
        try:    result[0] = fn()
        except Exception as e: err[0] = e
    t = threading.Thread(target=_run, daemon=True)
    t.start(); t.join(timeout)
    if t.is_alive(): return None, 'TIMEOUT'
    if err[0]:       return None, str(err[0])
    return result[0], None

print("=" * 70)
print(f"{'INDEX':<12} {'TEST':<35} RESULT")
print("=" * 70)

for exch, et, feed_scrip, chart_scrip, label in TESTS:

    # ── 1. Live market feed ───────────────────────────────────────────────────
    def _live(e=exch, et2=et, s=feed_scrip):
        return client.fetch_market_feed([{"Exch": e, "ExchangeType": et2, "ScripCode": int(s)}])

    r, err = run_with_timeout(_live)
    if err:
        print(f"{label:<12} {'live feed':<35} {err}")
    elif r:
        item  = r[0] if isinstance(r, list) else r
        print(f"{label:<12} {'live feed':<35} keys={sorted(item.keys())}")
        print(f"{'':12} {'':35} LTP={item.get('LastRate') or item.get('LTP')}  "
              f"O={item.get('OpenRate') or item.get('Open')}  "
              f"H={item.get('High') or item.get('HighRate')}  "
              f"L={item.get('Low') or item.get('LowRate')}  "
              f"PrevClose={item.get('PreviousClose') or item.get('CloseRate')}")
    else:
        print(f"{label:<12} {'live feed':<35} empty")

    # ── 2. Historical daily ───────────────────────────────────────────────────
    for scrip, tag in [(feed_scrip, f'hist 1d feed({feed_scrip})'),
                       (chart_scrip, f'hist 1d chart({chart_scrip})')]:
        def _hist(e=exch, et2=et, s=scrip):
            return client.historical_data(e, et2, int(s), '1d', FROM_DATE, TO_DATE)
        df, err = run_with_timeout(_hist, timeout=10)
        if err:
            print(f"{label:<12} {tag:<35} {err}")
        elif df is None or len(df) == 0:
            print(f"{label:<12} {tag:<35} empty")
        else:
            last = df.iloc[-1]
            print(f"{label:<12} {tag:<35} rows={len(df)}  cols={list(df.columns)}")
            print(f"{'':12} {'  last row':<35} {dict(last)}")

    print("-" * 70)

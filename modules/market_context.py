"""
market_context.py — fetch global market context for S/R AI analysis.
Pulls GIFT Nifty (real), India VIX, Dollar Index, Crude Oil (prev + current)
and top 5 India market news headlines from free public sources.
"""
import requests
import json
from datetime import datetime, timezone, timedelta

_IST     = timezone(timedelta(hours=5, minutes=30))
_TIMEOUT = 8

_BROWSER_HEADS = {
    'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                   'AppleWebKit/537.36 (KHTML, like Gecko) '
                   'Chrome/124.0.0.0 Safari/537.36'),
    'Accept':          'application/json, text/plain, */*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer':         'https://www.nseindia.com/',
}


# ── Real GIFT Nifty from NSE India ────────────────────────────────────────────
def _gift_nifty():
    """Fetch actual GIFT Nifty (NSE IFSC) prev close + current from NSE India."""
    try:
        sess = requests.Session()
        # Warm up cookies
        sess.get('https://www.nseindia.com', headers=_BROWSER_HEADS, timeout=_TIMEOUT)
        resp = sess.get(
            'https://www.nseindia.com/api/quote-derivative?symbol=GIFTNIFTY',
            headers=_BROWSER_HEADS, timeout=_TIMEOUT
        )
        data = resp.json()
        info = data.get('info', {})
        current = float(info.get('lastPrice', 0) or 0)
        prev    = float(info.get('previousClose', 0) or 0)
        if current == 0:
            # Try alternate key
            fut = data.get('stocks', [{}])[0].get('metadata', {})
            current = float(fut.get('lastPrice', 0) or 0)
            prev    = float(fut.get('previousClose', 0) or 0)
        chg_pct = round((current - prev) / prev * 100, 2) if prev else 0
        return {'label': 'GIFT Nifty', 'prev': round(prev, 2),
                'current': round(current, 2), 'change_pct': chg_pct}
    except Exception as e:
        # Fallback: try Yahoo Finance SGX / Nifty futures
        return _yf_quote('NIFTY_FUT.NS', 'GIFT Nifty (YF fallback)')


# ── Yahoo Finance quote ───────────────────────────────────────────────────────
def _yf_quote(symbol, label):
    """Return {'label', 'prev', 'current', 'change_pct'} or error dict."""
    try:
        url  = f'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=5d'
        resp = requests.get(url,
                            headers={'User-Agent': 'Mozilla/5.0'},
                            timeout=_TIMEOUT)
        data = resp.json()
        res  = data['chart']['result'][0]
        meta = res['meta']
        closes = [c for c in res['indicators']['quote'][0].get('close', []) if c]
        current = float(meta.get('regularMarketPrice') or meta.get('previousClose') or 0)
        prev    = float(closes[-2]) if len(closes) >= 2 else float(meta.get('previousClose') or 0)
        chg_pct = round((current - prev) / prev * 100, 2) if prev else 0
        return {'label': label, 'prev': round(prev, 2),
                'current': round(current, 2), 'change_pct': chg_pct}
    except Exception as e:
        return {'label': label, 'prev': 0, 'current': 0,
                'change_pct': 0, 'error': str(e)[:60]}


# ── Top 5 India market news via Google News RSS ───────────────────────────────
def _top_news(n=5):
    """Return list of up to n dicts with 'title' and 'pub' keys."""
    try:
        import xml.etree.ElementTree as ET
        url = ('https://news.google.com/rss/search'
               '?q=nifty+sensex+india+stock+market&hl=en-IN&gl=IN&ceid=IN:en')
        resp = requests.get(url,
                            headers={
                                'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                                               'AppleWebKit/537.36 (KHTML, like Gecko) '
                                               'Chrome/124.0.0.0 Safari/537.36'),
                                'Accept': 'application/rss+xml,application/xml,text/xml,*/*',
                            },
                            timeout=_TIMEOUT)
        resp.raise_for_status()

        # Parse XML — try raw bytes first, then explicit UTF-8 text
        try:
            root = ET.fromstring(resp.content)
        except ET.ParseError:
            root = ET.fromstring(resp.text.encode('utf-8'))

        items = root.findall('.//item')[:n]
        out   = []
        for item in items:
            # Try direct findtext first, then iterate children (handles namespaced tags)
            title = item.findtext('title')
            if not title:
                for child in item:
                    tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                    if tag.lower() == 'title':
                        title = child.text
                        break

            title = (title or '').strip()
            if not title:
                continue

            # Strip source attribution: "Headline - Source Name"
            title = title.split(' - ')[0].strip()
            if not title:
                continue

            pub = (item.findtext('pubDate') or '')[:16].strip()
            out.append({'title': title, 'pub': pub})

        return out if out else [{'title': 'No market news available', 'pub': ''}]

    except Exception as e:
        print(f'[NEWS] fetch error: {e}')
        return [{'title': f'News unavailable ({str(e)[:60]})', 'pub': ''}]


# ── Main entry ────────────────────────────────────────────────────────────────
def get_market_context():
    """
    Returns {
      'quotes': [{'label','prev','current','change_pct'}, ...],
      'news':   [{'title','pub'}, ...],
      'as_text': str
    }
    """
    quotes = [
        _gift_nifty(),
        _yf_quote('^INDIAVIX', 'India VIX'),
        _yf_quote('DX-Y.NYB',  'Dollar Index'),
        _yf_quote('CL=F',      'Crude Oil (WTI)'),
        _yf_quote('INR=X',     'USD/INR'),
    ]
    news = _top_news(5)

    lines = ['── Global Context ──────────────────────']
    for q in quotes:
        arrow = '▲' if q['change_pct'] >= 0 else '▼'
        sign  = '+' if q['change_pct'] >= 0 else ''
        lines.append(
            f"{q['label']:<22} Prev: {q['prev']:<10}  Now: {q['current']:<10}  "
            f"{arrow} {sign}{q['change_pct']}%"
        )
    lines.append('')
    lines.append('── Top 5 Market News ───────────────────')
    for i, h in enumerate(news, 1):
        lines.append(f"{i}. {h['title']}")

    return {'quotes': quotes, 'news': news, 'as_text': '\n'.join(lines)}

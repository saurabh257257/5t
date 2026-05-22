"""
market_context.py — fetch global market context for S/R AI analysis.
Pulls GIFT Nifty, India VIX, Dollar Index, Crude Oil, USD/INR
and multi-category news (India markets, crude/energy, global/US, commodity/tax).
"""
import requests
import json
import concurrent.futures
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime as _parse_rfc

_IST          = timezone(timedelta(hours=5, minutes=30))
_TIMEOUT      = 8
_NEWS_TIMEOUT = 6

_BROWSER_HEADS = {
    'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                   'AppleWebKit/537.36 (KHTML, like Gecko) '
                   'Chrome/124.0.0.0 Safari/537.36'),
    'Accept':          'application/json, text/plain, */*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer':         'https://www.nseindia.com/',
}

_NEWS_HEADS = {
    'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                   'AppleWebKit/537.36 (KHTML, like Gecko) '
                   'Chrome/124.0.0.0 Safari/537.36'),
    'Accept': 'application/rss+xml,application/xml,text/xml,*/*',
}

# (display_label, google_news_query, max_items_per_category)
_NEWS_CATEGORIES = [
    ('India Markets',   'nifty+sensex+BSE+NSE+india+stock+market+midcap',     3),
    ('Crude / Energy',  'crude+oil+brent+WTI+OPEC+energy+natural+gas',        2),
    ('Global Markets',  'dow+jones+nasdaq+sp500+wall+street+US+market+global', 2),
    ('Commodity / Tax', 'gold+silver+commodity+india+RBI+tax+budget+economy', 2),
]


# ── Real GIFT Nifty from NSE India ────────────────────────────────────────────
def _gift_nifty():
    try:
        sess = requests.Session()
        sess.get('https://www.nseindia.com', headers=_BROWSER_HEADS, timeout=_TIMEOUT)
        resp = sess.get(
            'https://www.nseindia.com/api/quote-derivative?symbol=GIFTNIFTY',
            headers=_BROWSER_HEADS, timeout=_TIMEOUT
        )
        data    = resp.json()
        info    = data.get('info', {})
        current = float(info.get('lastPrice', 0) or 0)
        prev    = float(info.get('previousClose', 0) or 0)
        if current == 0:
            fut     = data.get('stocks', [{}])[0].get('metadata', {})
            current = float(fut.get('lastPrice', 0) or 0)
            prev    = float(fut.get('previousClose', 0) or 0)
        if current > 0:
            chg_pct = round((current - prev) / prev * 100, 2) if prev else 0
            return {'label': 'GIFT Nifty', 'prev': round(prev, 2),
                    'current': round(current, 2), 'change_pct': chg_pct}
        raise ValueError('NSE returned 0')
    except Exception:
        r = _yf_quote('^NSEI', 'GIFT Nifty')
        if r['current'] == 0:
            r = _yf_quote('NIFTY.NS', 'GIFT Nifty (~)')
        return r


# ── Yahoo Finance quote ───────────────────────────────────────────────────────
def _yf_quote(symbol, label):
    try:
        url  = f'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=5d'
        resp = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=_TIMEOUT)
        data = resp.json()
        res  = data['chart']['result'][0]
        meta = res['meta']
        closes  = [c for c in res['indicators']['quote'][0].get('close', []) if c]
        current = float(meta.get('regularMarketPrice') or meta.get('previousClose') or 0)
        prev    = float(closes[-2]) if len(closes) >= 2 else float(meta.get('previousClose') or 0)
        chg_pct = round((current - prev) / prev * 100, 2) if prev else 0
        return {'label': label, 'prev': round(prev, 2),
                'current': round(current, 2), 'change_pct': chg_pct}
    except Exception as e:
        return {'label': label, 'prev': 0, 'current': 0,
                'change_pct': 0, 'error': str(e)[:60]}


# ── Single-category RSS news fetch ───────────────────────────────────────────
def _fetch_category(query, label, n=3):
    """Return list of {category, title, pub} for one Google News RSS query."""
    try:
        url  = (f'https://news.google.com/rss/search'
                f'?q={query}&hl=en-IN&gl=IN&ceid=IN:en')
        resp = requests.get(url, headers=_NEWS_HEADS, timeout=_NEWS_TIMEOUT)
        resp.raise_for_status()

        try:
            root = ET.fromstring(resp.content)
        except ET.ParseError:
            root = ET.fromstring(resp.text.encode('utf-8'))

        now_ist = datetime.now(_IST)
        cutoff  = now_ist - timedelta(hours=48)

        out = []
        for item in root.findall('.//item'):
            if len(out) >= n:
                break

            # Extract title
            title = item.findtext('title')
            if not title:
                for child in item:
                    tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                    if tag.lower() == 'title':
                        title = child.text
                        break
            title = (title or '').strip().split(' - ')[0].strip()
            if not title:
                continue

            # Date filter
            pub_raw = (item.findtext('pubDate') or '').strip()
            pub_lbl = ''
            try:
                pub_dt = _parse_rfc(pub_raw).astimezone(_IST)
                if pub_dt < cutoff:
                    continue
                pub_lbl = pub_dt.strftime('%d %b %H:%M')
            except Exception:
                pass  # include anyway if date unreadable

            out.append({'category': label, 'title': title, 'pub': pub_lbl})

        return out
    except Exception as e:
        print(f'[NEWS] {label} error: {e}')
        return []


# ── Multi-category news (parallel) ───────────────────────────────────────────
def _multi_category_news():
    """Fetch all news categories in parallel; return flat list ordered by category."""
    order = {lbl: i for i, (lbl, _, _) in enumerate(_NEWS_CATEGORIES)}
    all_items = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        futures = {
            ex.submit(_fetch_category, q, lbl, n): lbl
            for lbl, q, n in _NEWS_CATEGORIES
        }
        for fut in concurrent.futures.as_completed(futures):
            try:
                all_items.extend(fut.result())
            except Exception as e:
                print(f'[NEWS] parallel error: {e}')

    all_items.sort(key=lambda x: order.get(x.get('category', ''), 99))
    return all_items or [{'category': '', 'title': 'No recent market news available', 'pub': ''}]


# ── Main entry ────────────────────────────────────────────────────────────────
def get_market_context():
    """
    Returns {
      'quotes': [{'label','prev','current','change_pct'}, ...],
      'news':   [{'category','title','pub'}, ...],
      'as_text': str
    }
    Quotes are fetched in parallel; news categories are fetched in parallel.
    """
    # Parallel quote fetches
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
        f_gift  = ex.submit(_gift_nifty)
        f_vix   = ex.submit(_yf_quote, '^INDIAVIX', 'India VIX')
        f_dxy   = ex.submit(_yf_quote, 'DX-Y.NYB',  'Dollar Index')
        f_crude = ex.submit(_yf_quote, 'CL=F',      'Crude Oil (WTI)')
        f_inr   = ex.submit(_yf_quote, 'INR=X',     'USD/INR')

    _quote_map = [
        (f_gift,  'GIFT Nifty'),
        (f_vix,   'India VIX'),
        (f_dxy,   'Dollar Index'),
        (f_crude, 'Crude Oil (WTI)'),
        (f_inr,   'USD/INR'),
    ]
    quotes = []
    for fut, default_lbl in _quote_map:
        try:
            quotes.append(fut.result())
        except Exception as e:
            quotes.append({'label': default_lbl, 'prev': 0, 'current': 0,
                           'change_pct': 0, 'error': str(e)[:60]})

    # Parallel multi-category news
    news = _multi_category_news()

    # Build as_text for Claude prompts
    lines = ['── Global Context ──────────────────────']
    for q in quotes:
        arrow = '▲' if q['change_pct'] >= 0 else '▼'
        sign  = '+' if q['change_pct'] >= 0 else ''
        lines.append(
            f"{q['label']:<22} Prev: {q['prev']:<10}  Now: {q['current']:<10}  "
            f"{arrow} {sign}{q['change_pct']}%"
        )
    lines.append('')
    lines.append('── Market News ─────────────────────────')
    prev_cat = None
    for h in news:
        cat = h.get('category', '')
        if cat and cat != prev_cat:
            lines.append(f'\n[{cat}]')
            prev_cat = cat
        lines.append(f"  • {h['title']}")

    return {'quotes': quotes, 'news': news, 'as_text': '\n'.join(lines)}

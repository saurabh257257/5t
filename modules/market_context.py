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
    """Fetch GIFT Nifty — NSE India first, then Nifty 50 (^NSEI) as fallback."""
    try:
        sess = requests.Session()
        sess.get('https://www.nseindia.com', headers=_BROWSER_HEADS, timeout=_TIMEOUT)
        resp = sess.get(
            'https://www.nseindia.com/api/quote-derivative?symbol=GIFTNIFTY',
            headers=_BROWSER_HEADS, timeout=_TIMEOUT
        )
        data = resp.json()
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
        # NSE returned 0 — fall through to Yahoo
        raise ValueError('NSE returned 0')
    except Exception:
        # Fallback: Nifty 50 spot from Yahoo Finance (most reliable)
        r = _yf_quote('^NSEI', 'Nifty 50')
        if r['current'] == 0:
            # Last resort: try NIFTY futures symbol
            r = _yf_quote('NIFTY.NS', 'GIFT Nifty (~)')
        return r


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

        from email.utils import parsedate_to_datetime as _parse_rfc
        now_ist   = datetime.now(_IST)
        cutoff    = now_ist - timedelta(hours=24)  # last 24 hours

        all_items = root.findall('.//item')
        out       = []
        for item in all_items:
            if len(out) >= n:
                break

            # Extract title (handle namespaced tags)
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

            # Filter: only items published in the last 24 hours (IST)
            pub_raw = (item.findtext('pubDate') or '').strip()
            pub_lbl = pub_raw[:16]
            try:
                pub_dt  = _parse_rfc(pub_raw).astimezone(_IST)
                if pub_dt < cutoff:
                    continue   # too old — skip
                pub_lbl = pub_dt.strftime('%d %b %H:%M')
            except Exception:
                pass  # can't parse date — include anyway

            out.append({'title': title, 'pub': pub_lbl})

        # If nothing in last 24h (weekend/holiday), loosen to last 48h
        if not out:
            cutoff48 = now_ist - timedelta(hours=48)
            for item in all_items[:n]:
                title = item.findtext('title') or ''
                title = title.split(' - ')[0].strip()
                if not title:
                    continue
                pub_raw = (item.findtext('pubDate') or '').strip()
                pub_lbl = pub_raw[:16]
                try:
                    pub_dt  = _parse_rfc(pub_raw).astimezone(_IST)
                    if pub_dt >= cutoff48:
                        pub_lbl = pub_dt.strftime('%d %b %H:%M')
                        out.append({'title': title, 'pub': pub_lbl})
                except Exception:
                    out.append({'title': title, 'pub': pub_lbl})

        return out[:n] if out else [{'title': 'No recent market news available', 'pub': ''}]

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

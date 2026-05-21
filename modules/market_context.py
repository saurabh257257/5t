"""
market_context.py — fetch global market context for S/R AI analysis.
Pulls GIFT Nifty, India VIX, Dollar Index, Crude Oil (prev + current)
and top 5 India market news headlines from free public sources.
"""
import requests
import json
from datetime import datetime, timezone, timedelta

_IST   = timezone(timedelta(hours=5, minutes=30))
_HEADS = {'User-Agent': 'Mozilla/5.0 (compatible; MarketBot/1.0)'}
_TIMEOUT = 6


# ── Yahoo Finance quote (prev close + current) ─────────────────────────────────
def _yf_quote(symbol, label):
    """Return {'label', 'prev', 'current', 'change_pct'} or None on failure."""
    try:
        url  = f'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=5d'
        resp = requests.get(url, headers=_HEADS, timeout=_TIMEOUT)
        data = resp.json()
        result = data['chart']['result'][0]
        meta   = result['meta']
        closes = result['indicators']['quote'][0].get('close', [])
        closes = [c for c in closes if c is not None]
        current  = float(meta.get('regularMarketPrice') or meta.get('previousClose') or 0)
        prev     = float(closes[-2]) if len(closes) >= 2 else float(meta.get('previousClose') or 0)
        chg_pct  = round((current - prev) / prev * 100, 2) if prev else 0
        return {'label': label, 'prev': round(prev, 2), 'current': round(current, 2), 'change_pct': chg_pct}
    except Exception as e:
        return {'label': label, 'prev': 0, 'current': 0, 'change_pct': 0, 'error': str(e)[:60]}


# ── Top 5 India market news via Google News RSS ────────────────────────────────
def _top_news(n=5):
    """Return list of up to n headline strings."""
    try:
        import xml.etree.ElementTree as ET
        url  = ('https://news.google.com/rss/search'
                '?q=nifty+sensex+india+stock+market&hl=en-IN&gl=IN&ceid=IN:en')
        resp = requests.get(url, headers=_HEADS, timeout=_TIMEOUT)
        root = ET.fromstring(resp.content)
        items = root.findall('.//item')[:n]
        headlines = []
        for item in items:
            title = item.findtext('title') or ''
            # Google News titles look like "Headline - Source"
            title = title.split(' - ')[0].strip()
            if title:
                headlines.append(title)
        return headlines
    except Exception as e:
        return [f'(news fetch failed: {e})']


# ── Main entry ─────────────────────────────────────────────────────────────────
def get_market_context():
    """
    Returns a dict:
    {
      'quotes': [{'label','prev','current','change_pct'}, ...],
      'news':   ['headline1', ...],
      'as_text': '...'   ← formatted string ready to paste into a prompt
    }
    """
    symbols = [
        ('^NSEI',    'GIFT Nifty / Nifty Fut'),  # best proxy available on YF
        ('^INDIAVIX','India VIX'),
        ('DX-Y.NYB', 'Dollar Index (DXY)'),
        ('CL=F',     'Crude Oil (WTI)'),
    ]
    quotes = [_yf_quote(sym, lbl) for sym, lbl in symbols]
    news   = _top_news(5)

    # Format as readable text block
    lines = ['── Global Context ──────────────────────']
    for q in quotes:
        arrow  = '▲' if q['change_pct'] >= 0 else '▼'
        sign   = '+' if q['change_pct'] >= 0 else ''
        lines.append(
            f"{q['label']:<30} Prev: {q['prev']:<10}  Now: {q['current']:<10}  {arrow} {sign}{q['change_pct']}%"
        )
    lines.append('')
    lines.append('── Top 5 Market News ───────────────────')
    for i, h in enumerate(news, 1):
        lines.append(f"{i}. {h}")

    return {'quotes': quotes, 'news': news, 'as_text': '\n'.join(lines)}

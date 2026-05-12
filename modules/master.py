import os
import pandas as pd
import requests
from io import StringIO
from datetime import datetime, timedelta

MASTER_URL = "https://openapi.5paisa.com/VendorsAPI/Service1.svc/ScripMaster/segment/All"
DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
MASTER_FILE = os.path.join(DATA_DIR, 'master.csv')

_df = None
_columns = {}  # normalized column name map


def _detect_columns(df):
    cols = {c.lower(): c for c in df.columns}
    return {
        "code":   next((v for k, v in cols.items() if 'scripcode' in k or ('scrip' in k and 'code' in k)), None),
        "name":   next((v for k, v in cols.items() if k == 'name'), None),
        "short":  next((v for k, v in cols.items() if 'short' in k and 'name' in k), None),
        "exch":   next((v for k, v in cols.items() if k == 'exch'), None),
        "type":   next((v for k, v in cols.items() if 'exchtype' in k or k == 'exchangetype'), None),
        "series": next((v for k, v in cols.items() if k == 'series'), None),
        "expiry": next((v for k, v in cols.items() if k == 'expiry'), None),
        "strike": next((v for k, v in cols.items() if 'strike' in k), None),
        "lot":    next((v for k, v in cols.items() if 'lot' in k and 'size' in k), None),
    }


def _is_stale():
    if not os.path.exists(MASTER_FILE):
        return True
    age = datetime.now() - datetime.fromtimestamp(os.path.getmtime(MASTER_FILE))
    return age > timedelta(hours=24)


def load_master():
    global _df, _columns
    if _df is not None:
        return _df
    os.makedirs(DATA_DIR, exist_ok=True)
    if _is_stale():
        _df = refresh_master()
    else:
        _df = pd.read_csv(MASTER_FILE, low_memory=False)
    _columns = _detect_columns(_df)
    return _df


def refresh_master():
    global _df, _columns
    os.makedirs(DATA_DIR, exist_ok=True)
    r = requests.get(MASTER_URL, timeout=60)
    r.raise_for_status()
    _df = pd.read_csv(StringIO(r.text), low_memory=False)
    _df.to_csv(MASTER_FILE, index=False)
    _columns = _detect_columns(_df)
    return _df


def get_status():
    return {"loaded": _df is not None, "rows": len(_df) if _df is not None else 0}


def browse_scrips(cat='all', query='', page=1, limit=50):
    df = load_master()
    c = _columns

    # Category filter
    if cat == 'equity' and c['type']:
        mask = df[c['type']].astype(str).str.upper() == 'C'
    elif cat == 'futures' and c['type'] and c['series']:
        mask = (df[c['type']].astype(str).str.upper() == 'D') & \
               (df[c['series']].astype(str).str.upper() == 'FUT')
    elif cat == 'options' and c['type'] and c['series']:
        mask = (df[c['type']].astype(str).str.upper() == 'D') & \
               (df[c['series']].astype(str).str.upper().isin(['CE', 'PE']))
    elif cat == 'commodity' and c['exch']:
        mask = df[c['exch']].astype(str).str.upper().isin(['M', 'MCX', 'N', 'B']) & \
               df[c['type']].astype(str).str.upper().isin(['U', 'Y', 'G']) \
               if c['type'] else df[c['exch']].astype(str).str.upper().isin(['M', 'MCX'])
    else:
        mask = pd.Series([True] * len(df), index=df.index)

    filtered = df[mask]

    # Search filter
    if query and len(query.strip()) >= 1:
        q = query.upper().strip()
        qmask = pd.Series([False] * len(filtered), index=filtered.index)
        if c['name']:
            qmask |= filtered[c['name']].astype(str).str.upper().str.contains(q, na=False)
        if c['short']:
            qmask |= filtered[c['short']].astype(str).str.upper().str.contains(q, na=False)
        if c['code']:
            qmask |= filtered[c['code']].astype(str).str.contains(q, na=False)
        filtered = filtered[qmask]

    if c['name']:
        filtered = filtered.sort_values(c['name'])

    total = len(filtered)
    start = (page - 1) * limit
    page_data = filtered.iloc[start:start + limit]
    keep = [v for v in [c['code'], c['name'], c['short'], c['exch'], c['type'], c['series'], c['expiry'], c['strike'], c['lot']] if v]
    return {
        'results': page_data[keep].fillna('').to_dict('records'),
        'total': total, 'page': page, 'has_more': (start + limit) < total
    }


def search_scrips(query, limit=25):
    df = load_master()
    c = _columns
    q = str(query).upper().strip()

    mask = pd.Series([False] * len(df), index=df.index)
    if c["name"]:
        mask |= df[c["name"]].astype(str).str.upper().str.contains(q, na=False)
    if c["short"]:
        mask |= df[c["short"]].astype(str).str.upper().str.contains(q, na=False)
    if c["code"]:
        mask |= df[c["code"]].astype(str).str.contains(q, na=False)

    rows = df[mask].head(limit)
    keep = [v for v in [c["code"], c["name"], c["short"], c["exch"], c["type"], c["series"], c["expiry"], c["strike"], c["lot"]] if v]
    return rows[keep].fillna("").to_dict("records")


def get_scrip_info(scripcode):
    df = load_master()
    c = _columns
    if not c["code"]:
        return None
    row = df[df[c["code"]].astype(str) == str(scripcode)]
    if row.empty:
        return None
    return row.iloc[0].to_dict()


def is_fno(scrip_row):
    c = _columns
    exch_type = scrip_row.get(c.get("type", ""), "")
    series = scrip_row.get(c.get("series", ""), "")
    return str(exch_type).upper() == "D" or str(series).upper() in ["FUT", "CE", "PE", "OPT"]

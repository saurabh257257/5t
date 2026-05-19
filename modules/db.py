import sqlite3
import json
import os
from datetime import datetime, timezone, timedelta

_IST = timezone(timedelta(hours=5, minutes=30))

_DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'dashboard.db')


def _conn():
    c = sqlite3.connect(_DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    with _conn() as c:
        c.execute('''
            CREATE TABLE IF NOT EXISTS sr_levels (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                index_id    TEXT    NOT NULL,
                saved_at    TEXT    NOT NULL,
                ltp         REAL,
                supports    TEXT,
                resistances TEXT,
                valid_today TEXT,
                verdict     TEXT
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS chain_snapshots (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                index_id     TEXT    NOT NULL,
                expiry_label TEXT,
                expiry_ts    INTEGER,
                ltp          REAL,
                prev_close   REAL,
                change_abs   REAL,
                change_pct   REAL,
                pcr          REAL,
                max_pain     REAL,
                ce_oi        INTEGER,
                pe_oi        INTEGER,
                summary      TEXT,
                saved_at     TEXT NOT NULL
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS chain_analysis (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                index_id     TEXT    NOT NULL,
                expiry_label TEXT,
                expiry_ts    INTEGER,
                date         TEXT    NOT NULL,
                time         TEXT    NOT NULL,
                ltp          REAL,
                pcr          REAL,
                max_pain     REAL,
                analysis     TEXT    NOT NULL,
                saved_at     TEXT    NOT NULL
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS sr_alerts (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                index_id     TEXT    NOT NULL,
                level        REAL    NOT NULL,
                level_type   TEXT    NOT NULL,
                ltp          REAL    NOT NULL,
                distance_pct REAL    NOT NULL,
                alerted_at   TEXT    NOT NULL
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS breach_alerts (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                index_id   TEXT    NOT NULL,
                level      REAL    NOT NULL,
                level_type TEXT    NOT NULL,
                prev_ltp   REAL    NOT NULL,
                ltp        REAL    NOT NULL,
                alerted_at TEXT    NOT NULL
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS market_summary (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                index_id     TEXT    NOT NULL,
                expiry_label TEXT,
                date         TEXT    NOT NULL,
                time         TEXT    NOT NULL,
                ltp          REAL,
                pcr          REAL,
                max_pain     REAL,
                analysis     TEXT    NOT NULL,
                structured   TEXT,
                saved_at     TEXT    NOT NULL
            )
        ''')
        # Migrate: add structured column if table already existed without it
        try:
            c.execute('ALTER TABLE market_summary ADD COLUMN structured TEXT')
        except Exception:
            pass  # column already exists
        c.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        ''')
        # Seed default settings
        defaults = [
            ('sr_monitor_enabled',      'true'),
            ('sr_monitor_freq_min',     '5'),
            ('sr_threshold_pct',        '0.3'),
            ('sr_monitor_indices',         'SENSEX,NIFTY,BANKNIFTY,FINNIFTY'),
            ('sr_monitor_market_hours',    'false'),
            ('market_update_enabled',      'false'),
            ('market_update_freq_min',     '5'),
            ('market_update_indices',      'SENSEX,NIFTY,BANKNIFTY,FINNIFTY'),
            ('market_update_market_hours', 'false'),
            ('breach_monitor_enabled',     'false'),
            ('breach_monitor_freq_min',    '2'),
            ('breach_monitor_indices',     'SENSEX,NIFTY,BANKNIFTY,FINNIFTY'),
            ('breach_monitor_market_hours','false'),
        ]
        for key, val in defaults:
            c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', (key, val))
        c.commit()


# ── S/R Levels ─────────────────────────────────────────────────────────────────

def save_sr(index_id, ltp, supports, resistances, valid_today, verdict):
    with _conn() as c:
        cur = c.execute(
            '''INSERT INTO sr_levels
               (index_id, saved_at, ltp, supports, resistances, valid_today, verdict)
               VALUES (?, ?, ?, ?, ?, ?, ?)''',
            (
                index_id,
                datetime.now(_IST).strftime('%Y-%m-%d %H:%M'),
                ltp,
                json.dumps(supports),
                json.dumps(resistances),
                json.dumps(valid_today),
                verdict,
            )
        )
        c.commit()
        return cur.lastrowid


def delete_sr(record_id):
    with _conn() as c:
        c.execute('DELETE FROM sr_levels WHERE id = ?', (record_id,))
        c.commit()
        return c.execute('SELECT changes()').fetchone()[0]


def get_sr_history(index_id, limit=10):
    with _conn() as c:
        rows = c.execute(
            'SELECT * FROM sr_levels WHERE index_id=? ORDER BY saved_at DESC LIMIT ?',
            (index_id, limit)
        ).fetchall()
        result = []
        for r in rows:
            result.append({
                'id':          r['id'],
                'index_id':    r['index_id'],
                'saved_at':    r['saved_at'],
                'ltp':         r['ltp'],
                'supports':    json.loads(r['supports']    or '[]'),
                'resistances': json.loads(r['resistances'] or '[]'),
                'valid_today': json.loads(r['valid_today'] or '[]'),
                'verdict':     r['verdict'],
            })
        return result


# ── Chain Analysis (user-triggered) ───────────────────────────────────────────

def save_chain_analysis(index_id, expiry_label, expiry_ts, ltp, pcr, max_pain, analysis):
    now = datetime.now(_IST)
    with _conn() as c:
        cur = c.execute('''
            INSERT INTO chain_analysis
            (index_id, expiry_label, expiry_ts, date, time, ltp, pcr, max_pain, analysis, saved_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            index_id, expiry_label, int(expiry_ts) if expiry_ts else 0,
            now.strftime('%Y-%m-%d'), now.strftime('%H:%M'),
            ltp, pcr, max_pain, analysis,
            now.strftime('%Y-%m-%d %H:%M:%S'),
        ))
        c.commit()
        return cur.lastrowid


def get_chain_analysis_history(index_id, limit=20):
    with _conn() as c:
        rows = c.execute(
            'SELECT * FROM chain_analysis WHERE index_id=? ORDER BY saved_at DESC LIMIT ?',
            (index_id, limit)
        ).fetchall()
        return [dict(r) for r in rows]


def delete_chain_analysis(record_id):
    with _conn() as c:
        c.execute('DELETE FROM chain_analysis WHERE id = ?', (record_id,))
        c.commit()
        return c.execute('SELECT changes()').fetchone()[0]


# ── Market Summary (enhanced chain analysis per segment) ──────────────────────

def save_market_summary(index_id, expiry_label, ltp, pcr, max_pain, analysis, structured=None):
    now = datetime.now(_IST)
    with _conn() as c:
        cur = c.execute('''
            INSERT INTO market_summary
            (index_id, expiry_label, date, time, ltp, pcr, max_pain, analysis, structured, saved_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            index_id, expiry_label,
            now.strftime('%Y-%m-%d'), now.strftime('%H:%M'),
            ltp, pcr, max_pain, analysis, structured,
            now.strftime('%Y-%m-%d %H:%M:%S'),
        ))
        c.commit()
        return cur.lastrowid


def get_latest_market_summary(index_id):
    """Return the most recent market summary for an index, or None."""
    with _conn() as c:
        row = c.execute(
            'SELECT * FROM market_summary WHERE index_id=? ORDER BY saved_at DESC LIMIT 1',
            (index_id,)
        ).fetchone()
        return dict(row) if row else None


def get_today_market_summary(index_id):
    """Return the most recent summary saved today (IST), or None."""
    today = datetime.now(_IST).strftime('%Y-%m-%d')
    with _conn() as c:
        row = c.execute(
            'SELECT * FROM market_summary WHERE index_id=? AND date=? ORDER BY saved_at DESC LIMIT 1',
            (index_id, today)
        ).fetchone()
        return dict(row) if row else None


def get_market_summary_history(index_id, limit=20):
    with _conn() as c:
        rows = c.execute(
            'SELECT * FROM market_summary WHERE index_id=? ORDER BY saved_at DESC LIMIT ?',
            (index_id, limit)
        ).fetchall()
        return [dict(r) for r in rows]


def delete_market_summary(record_id):
    with _conn() as c:
        c.execute('DELETE FROM market_summary WHERE id = ?', (record_id,))
        c.commit()
        return c.execute('SELECT changes()').fetchone()[0]


# ── SR Alerts ─────────────────────────────────────────────────────────────────

def save_sr_alert(index_id, level, level_type, ltp, distance_pct):
    with _conn() as c:
        cur = c.execute('''
            INSERT INTO sr_alerts (index_id, level, level_type, ltp, distance_pct, alerted_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (index_id, level, level_type, ltp, distance_pct,
              datetime.now(_IST).strftime('%Y-%m-%d %H:%M:%S')))
        c.commit()
        return cur.lastrowid


def get_sr_alerts(limit=20):
    with _conn() as c:
        rows = c.execute(
            'SELECT * FROM sr_alerts ORDER BY alerted_at DESC LIMIT ?', (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def was_recently_alerted(index_id, level, minutes=30):
    """True if an alert for this index+level was already saved within `minutes`."""
    with _conn() as c:
        cutoff = (datetime.now(_IST) - timedelta(minutes=minutes)).strftime('%Y-%m-%d %H:%M:%S')
        row = c.execute(
            '''SELECT id FROM sr_alerts
               WHERE index_id=? AND ABS(level - ?) < 1 AND alerted_at > ?''',
            (index_id, level, cutoff)
        ).fetchone()
        return row is not None


def cleanup_old_alerts(days=30):
    with _conn() as c:
        cutoff = (datetime.now(_IST) - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
        c.execute('DELETE FROM sr_alerts WHERE alerted_at < ?', (cutoff,))
        c.commit()


# ── Breach Alerts ─────────────────────────────────────────────────────────────

def save_breach_alert(index_id, level, level_type, prev_ltp, ltp):
    with _conn() as c:
        cur = c.execute('''
            INSERT INTO breach_alerts (index_id, level, level_type, prev_ltp, ltp, alerted_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (index_id, level, level_type, prev_ltp, ltp,
              datetime.now(_IST).strftime('%Y-%m-%d %H:%M:%S')))
        c.commit()
        return cur.lastrowid


def get_breach_alerts(index_id=None, limit=30):
    with _conn() as c:
        if index_id:
            rows = c.execute(
                'SELECT * FROM breach_alerts WHERE index_id=? ORDER BY alerted_at DESC LIMIT ?',
                (index_id, limit)
            ).fetchall()
        else:
            rows = c.execute(
                'SELECT * FROM breach_alerts ORDER BY alerted_at DESC LIMIT ?', (limit,)
            ).fetchall()
        return [dict(r) for r in rows]


def cleanup_old_breach_alerts(days=30):
    with _conn() as c:
        cutoff = (datetime.now(_IST) - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
        c.execute('DELETE FROM breach_alerts WHERE alerted_at < ?', (cutoff,))
        c.commit()


# ── Settings ──────────────────────────────────────────────────────────────────

def get_setting(key, default=''):
    with _conn() as c:
        row = c.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
        return row['value'] if row else default


def set_setting(key, value):
    with _conn() as c:
        c.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key, str(value)))
        c.commit()


# ── Auto chain snapshots ───────────────────────────────────────────────────────

def save_snapshot(index_id, expiry_label, expiry_ts, ltp, prev_close,
                  change_abs, change_pct, pcr, max_pain, ce_oi, pe_oi, summary):
    with _conn() as c:
        c.execute('''
            INSERT INTO chain_snapshots
            (index_id, expiry_label, expiry_ts, ltp, prev_close,
             change_abs, change_pct, pcr, max_pain, ce_oi, pe_oi, summary, saved_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (index_id, expiry_label, int(expiry_ts), ltp, prev_close,
              change_abs, change_pct, pcr, max_pain, ce_oi, pe_oi, summary,
              datetime.now(_IST).strftime('%Y-%m-%d %H:%M:%S')))
        c.commit()


def get_snapshots(index_id, limit=60):
    with _conn() as c:
        rows = c.execute(
            'SELECT * FROM chain_snapshots WHERE index_id=? ORDER BY saved_at DESC LIMIT ?',
            (index_id, limit)
        ).fetchall()
        return [dict(r) for r in rows]


def cleanup_old_snapshots(days=7):
    with _conn() as c:
        cutoff = (datetime.now(_IST) - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
        c.execute('DELETE FROM chain_snapshots WHERE saved_at < ?', (cutoff,))
        c.commit()

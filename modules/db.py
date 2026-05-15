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
        c.commit()


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
    """Delete snapshots older than N days to prevent DB bloat."""
    with _conn() as c:
        cutoff = (datetime.now(_IST) - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
        c.execute('DELETE FROM chain_snapshots WHERE saved_at < ?', (cutoff,))
        c.commit()

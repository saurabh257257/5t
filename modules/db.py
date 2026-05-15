import sqlite3
import json
import os
from datetime import datetime

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
        c.commit()


def save_sr(index_id, ltp, supports, resistances, valid_today, verdict):
    with _conn() as c:
        c.execute(
            '''INSERT INTO sr_levels
               (index_id, saved_at, ltp, supports, resistances, valid_today, verdict)
               VALUES (?, ?, ?, ?, ?, ?, ?)''',
            (
                index_id,
                datetime.now().strftime('%Y-%m-%d %H:%M'),
                ltp,
                json.dumps(supports),
                json.dumps(resistances),
                json.dumps(valid_today),
                verdict,
            )
        )
        c.commit()
        return c.lastrowid


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

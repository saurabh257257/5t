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

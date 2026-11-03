"""Durable local inbox and transactionally maintained demo metrics."""

import hashlib
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path

STATES = set('AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO'.split())
FIELDS = {'version', 'event_id', 'kind', 'event_time', 'state', 'item_value_cents', 'simulated'}


def validate(event):
    if not isinstance(event, dict) or set(event) != FIELDS:
        raise ValueError('Invalid event fields')
    if type(event['version']) is not int or event['version'] != 1:
        raise ValueError('Unsupported event version')
    if event['kind'] != 'historical_order_purchase' or event['simulated'] is not True:
        raise ValueError('Only simulated historical purchases are supported')
    if not isinstance(event['event_id'], str) or not re.fullmatch(r'[0-9a-f]{64}', event['event_id']):
        raise ValueError('Invalid event ID')
    stamp = event['event_time']
    if not isinstance(stamp, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}', stamp):
        raise ValueError('Invalid source timestamp')
    datetime.strptime(stamp, '%Y-%m-%d %H:%M:%S')
    if event['state'] not in STATES:
        raise ValueError('Invalid customer state')
    cents = event['item_value_cents']
    if type(cents) is not int or not 0 <= cents <= 10**12:
        raise ValueError('Invalid item value')
    return event


def canonical(event):
    return json.dumps(event, sort_keys=True, separators=(',', ':'))


def open_store(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('PRAGMA synchronous=FULL')
    db.executescript('''
        CREATE TABLE IF NOT EXISTS inbox (
            sequence INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT UNIQUE NOT NULL,
            payload TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','processed','rejected')),
            rejection TEXT,
            received_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            processed_at TEXT
        );
        CREATE INDEX IF NOT EXISTS pending_events ON inbox(status, sequence);
        CREATE TABLE IF NOT EXISTS daily_metrics (
            purchase_day TEXT NOT NULL,
            state TEXT NOT NULL,
            orders INTEGER NOT NULL,
            item_value_cents INTEGER NOT NULL,
            PRIMARY KEY(purchase_day, state)
        );
    ''')
    return db


def enqueue(db, event):
    payload = canonical(validate(event))
    with db:
        cursor = db.execute('INSERT INTO inbox(event_id,payload) VALUES (?,?) ON CONFLICT(event_id) DO NOTHING',
                            (event['event_id'], payload))
        if cursor.rowcount:
            return True
        previous = db.execute('SELECT payload FROM inbox WHERE event_id=?', (event['event_id'],)).fetchone()
        if previous['payload'] != payload:
            raise ValueError('Conflicting payload for an existing event ID')
        return False


def process_one(db):
    # Serialize local consumers. Aggregate write and acknowledgment commit together.
    db.execute('BEGIN IMMEDIATE')
    try:
        row = db.execute("SELECT * FROM inbox WHERE status='pending' ORDER BY sequence LIMIT 1").fetchone()
        if row is None:
            db.commit()
            return None
        try:
            event = validate(json.loads(row['payload']))
            if event['event_id'] != row['event_id']:
                raise ValueError('Event identity mismatch')
        except (ValueError, TypeError, KeyError):
            db.execute("UPDATE inbox SET status='rejected',rejection='invalid event contract',processed_at=CURRENT_TIMESTAMP WHERE sequence=?", (row['sequence'],))
            db.commit()
            return 'rejected'
        db.execute('''INSERT INTO daily_metrics VALUES (?,?,1,?)
            ON CONFLICT(purchase_day,state) DO UPDATE SET
            orders=orders+1,item_value_cents=item_value_cents+excluded.item_value_cents''',
                   (event['event_time'][:10], event['state'], event['item_value_cents']))
        db.execute("UPDATE inbox SET status='processed',processed_at=CURRENT_TIMESTAMP WHERE sequence=?", (row['sequence'],))
        db.commit()
        return 'processed'
    except BaseException:
        db.rollback()
        raise


def status(db):
    counts = {row['status']: row['n'] for row in db.execute('SELECT status,COUNT(*) n FROM inbox GROUP BY status')}
    totals = db.execute('SELECT COALESCE(SUM(orders),0) orders,COALESCE(SUM(item_value_cents),0) item_value_cents FROM daily_metrics').fetchone()
    return {'simulated': True, 'source': 'historical Olist replay',
            'timestamp_basis': 'source purchase time; timezone unspecified',
            'metric': 'all-status purchase item value; excludes freight; not delivered GMV or profit',
            'queue': {name: counts.get(name, 0) for name in ('pending', 'processed', 'rejected')},
            'totals': dict(totals),
            'daily_metrics': [dict(row) for row in db.execute('SELECT * FROM daily_metrics ORDER BY purchase_day,state')]}


def event_id(order_id):
    return hashlib.sha256(('olist-replay-v1:' + order_id).encode()).hexdigest()

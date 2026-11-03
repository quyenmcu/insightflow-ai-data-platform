import csv
import sqlite3
import tempfile
import unittest
from pathlib import Path

from streaming.replay import events
from streaming.store import canonical, enqueue, event_id, open_store, process_one, status


def purchase(order='one', value=1234, day='2018-01-01'):
    return {'version': 1, 'event_id': event_id(order), 'kind': 'historical_order_purchase',
            'event_time': day + ' 12:00:00', 'state': 'SP', 'item_value_cents': value, 'simulated': True}


class StreamingTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'events.sqlite'
        self.db = open_store(self.path)
        self.addCleanup(lambda: self.db.close())

    def test_duplicate_replay_after_restart_does_not_double_count(self):
        self.assertTrue(enqueue(self.db, purchase()))
        self.assertEqual(process_one(self.db), 'processed')
        self.db.close()
        self.db = open_store(self.path)
        self.assertFalse(enqueue(self.db, purchase()))
        self.assertIsNone(process_one(self.db))
        self.assertEqual(status(self.db)['totals'], {'orders': 1, 'item_value_cents': 1234})
        with self.assertRaisesRegex(ValueError, 'Conflicting'):
            enqueue(self.db, purchase(value=9999))

    def test_aggregate_and_acknowledgment_rollback_together(self):
        enqueue(self.db, purchase())
        self.db.execute("CREATE TRIGGER simulated_failure BEFORE UPDATE ON inbox BEGIN SELECT RAISE(ABORT, 'disk failure'); END")
        with self.assertRaises(sqlite3.DatabaseError):
            process_one(self.db)
        self.assertEqual(status(self.db)['queue']['pending'], 1)
        self.assertEqual(status(self.db)['totals']['orders'], 0)
        self.db.execute('DROP TRIGGER simulated_failure')
        self.assertEqual(process_one(self.db), 'processed')
        self.assertEqual(status(self.db)['totals']['orders'], 1)

    def test_invalid_events_rejected_without_blocking_next_event(self):
        self.db.execute('INSERT INTO inbox(event_id,payload) VALUES (?,?)', ('broken', '{'))
        self.db.commit()
        enqueue(self.db, purchase())
        self.assertEqual(process_one(self.db), 'rejected')
        self.assertEqual(process_one(self.db), 'processed')
        self.assertEqual(status(self.db)['queue'], {'pending': 0, 'processed': 1, 'rejected': 1})
        for changed in [{'simulated': False}, {'item_value_cents': -1}, {'item_value_cents': True}, {'event_time': '2018-02-30 12:00:00'}, {'state': 'XX'}, {'version': True}]:
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                enqueue(self.db, {**purchase(), **changed})

    def test_late_events_use_event_day_and_exact_cents(self):
        enqueue(self.db, purchase('later', 101, '2018-02-02'))
        enqueue(self.db, purchase('earlier', 202, '2018-01-01'))
        enqueue(self.db, purchase('same-day', 303, '2018-01-01'))
        while process_one(self.db):
            pass
        result = status(self.db)
        self.assertEqual(result['totals'], {'orders': 3, 'item_value_cents': 606})
        self.assertEqual(result['daily_metrics'][0]['item_value_cents'], 505)
        self.assertEqual(result['daily_metrics'][0]['purchase_day'], '2018-01-01')

    def test_replay_sorted_stable_and_omits_final_outcomes_and_ids(self):
        directory = Path(self.directory.name)
        sources = {
            'olist_customers_dataset.csv': [['customer_id', 'customer_state'], ['c1', 'SP']],
            'olist_order_items_dataset.csv': [['order_id', 'order_item_id', 'price'], ['o1', '1', '0.10'], ['o1', '2', '0.20']],
            'olist_orders_dataset.csv': [['order_id', 'customer_id', 'order_purchase_timestamp', 'order_status'], ['o1', 'c1', '2018-02-01 12:00:00', 'delivered'], ['o2', 'c1', '2018-01-01 12:00:00', 'canceled']],
        }
        for filename, data in sources.items():
            with (directory / filename).open('w', newline='') as output:
                csv.writer(output).writerows(data)
        replay = events(directory)
        self.assertEqual(replay, events(directory))
        self.assertEqual([event['item_value_cents'] for event in replay], [0, 30])
        self.assertLess(replay[0]['event_time'], replay[1]['event_time'])
        self.assertNotIn('delivered', canonical(replay[1]))
        self.assertNotIn('customer_id', replay[1])
        self.assertNotIn('order_id', replay[1])


if __name__ == '__main__':
    unittest.main()

"""Run replay and consumer in separate processes against one local SQLite inbox."""

import argparse
import json
import math
import time
from pathlib import Path

from .replay import events
from .store import enqueue, open_store, process_one, status


def main():
    parser = argparse.ArgumentParser(description='SIMULATED historical streaming demo; separate from batch')
    parser.add_argument('--db', type=Path, default=Path('data/processed/streaming/events.sqlite'))
    commands = parser.add_subparsers(dest='command', required=True)
    replay = commands.add_parser('replay', help='Replay purchases in source-time order')
    replay.add_argument('--data-dir', type=Path, default=Path('data/raw'))
    replay.add_argument('--limit', type=int, default=100)
    replay.add_argument('--rate', type=float, default=20, help='Events/second; zero runs without pacing')
    consume = commands.add_parser('consume', help='Apply pending events transactionally')
    consume.add_argument('--watch', action='store_true', help='Poll for new events until Ctrl+C')
    commands.add_parser('status', help='Print simulated queue and event-day metrics')
    args = parser.parse_args()
    if args.command == 'replay' and (args.limit < 1 or not math.isfinite(args.rate) or args.rate < 0):
        parser.error('limit must be positive; rate must be finite and nonnegative')
    db = open_store(args.db)
    try:
        if args.command == 'replay':
            selected = events(args.data_dir)[:args.limit]
            accepted = duplicates = 0
            for event in selected:
                if enqueue(db, event):
                    accepted += 1
                else:
                    duplicates += 1
                if args.rate:
                    time.sleep(1 / args.rate)
            print(json.dumps({'simulated': True, 'accepted': accepted, 'duplicates': duplicates}), flush=True)
        elif args.command == 'consume':
            processed = rejected = 0
            try:
                while True:
                    result = process_one(db)
                    if result == 'processed':
                        processed += 1
                    elif result == 'rejected':
                        rejected += 1
                    elif not args.watch:
                        break
                    else:
                        time.sleep(0.25)
                        continue
                    if args.watch:
                        print(json.dumps({'simulated': True, 'processed': processed, 'rejected': rejected}), flush=True)
            except KeyboardInterrupt:
                pass
            print(json.dumps({'simulated': True, 'processed': processed, 'rejected': rejected}), flush=True)
        else:
            print(json.dumps(status(db), indent=2))
    finally:
        db.close()


if __name__ == '__main__':
    main()

from collections import OrderedDict
from snapshot import Snapshot
from wal import WAL

import threading

class LRUCache:
    def __init__(self, capacity, snapshot_after):
        self.cache = OrderedDict()
        self.capacity = capacity
        self.snapshot_after = snapshot_after

        self.snapshot = Snapshot("snapshot.json")
        self.wal = WAL("WAL.log")
        self.ops_since_snapshot = 0
        self.seq = 0
        self.lock = threading.RLock()

    def get(self, key):
        with self.lock:
            if key not in self.cache:
                return -1
            self.cache.move_to_end(key)
            return self.cache[key]

    def put(self, key, value):
        with self.lock:
            self.seq += 1
            self.wal.append({"seq": self.seq, "key": key, "value": value})
            self._apply(key, value)
            self.ops_since_snapshot += 1
            if self.ops_since_snapshot >= self.snapshot_after:
                self.snapshot.save({
                    "seq": self.seq,
                    "cache": list(self.cache.items())
                })
                self.wal.rotate()
                self.ops_since_snapshot = 0

    def _recover(self):
        with self.lock:
            try:
                data = self.snapshot.load()
                snapshot_seq = data.get("seq", 0)
                self.cache = OrderedDict(data["cache"])
            except FileNotFoundError:
                snapshot_seq = 0
                self.cache = OrderedDict()
            self.seq = snapshot_seq
            for record in self.wal.replay():
                start_seq = record["seq"]
                key = record["key"]
                value = record["value"]
                if start_seq > snapshot_seq:
                    self._apply(key, value)
                    self.seq = max(self.seq, start_seq)
                    self.ops_since_snapshot += 1

    def _apply(self, key, value):
        self.cache[key] = value
        self.cache.move_to_end(key)

        if len(self.cache) > self.capacity:
            self.cache.popitem(last=False)
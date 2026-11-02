
import os
import tempfile
import threading
import unittest

from lru_cache import LRUCache


class TestLRUCache(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_dir = os.getcwd()
        os.chdir(self.temp_dir.name)
        self.caches = []

    def tearDown(self):
        # Close all WAL handles, even if a test fails.
        for cache in self.caches:
            cache.wal.close()

        os.chdir(self.original_dir)
        self.temp_dir.cleanup()

    def new_cache(self, capacity=1000, snapshot_after=10):
        cache = LRUCache(capacity, snapshot_after)
        cache._recover()
        self.caches.append(cache)
        return cache

    def restart_cache(self, capacity=1000, snapshot_after=10):
        # Simulate a clean application restart.
        return self.new_cache(capacity, snapshot_after)

    # -----------------------------------------
    # Basic LRU behavior
    # -----------------------------------------

    def test_basic_lru(self):
        cache = self.new_cache(capacity=2)

        cache.put(1, 100)
        cache.put(2, 200)

        self.assertEqual(cache.get(1), 100)

        # Key 1 is recently used, so key 2 is evicted.
        cache.put(3, 300)

        self.assertEqual(cache.get(1), 100)
        self.assertEqual(cache.get(2), -1)
        self.assertEqual(cache.get(3), 300)

    # -----------------------------------------
    # WAL recovery without snapshots
    # -----------------------------------------

    def test_wal_recovery(self):
        cache = self.new_cache(snapshot_after=1000)

        for i in range(1, 8):
            cache.put(i, i * 100)

        self.assertEqual(cache.seq, 7)

        recovered = self.restart_cache(snapshot_after=1000)

        for i in range(1, 8):
            self.assertEqual(recovered.get(i), i * 100)

        self.assertEqual(recovered.seq, 7)

    # -----------------------------------------
    # Snapshot creation and WAL rotation
    # -----------------------------------------

    def test_snapshot_and_rotation(self):
        cache = self.new_cache(snapshot_after=10)

        for i in range(1, 26):
            cache.put(i, i * 10)

        self.assertTrue(os.path.exists("snapshot.json"))
        self.assertTrue(os.path.exists("WAL.log"))

        self.assertEqual(cache.seq, 25)
        self.assertEqual(cache.ops_since_snapshot, 5)

        # Snapshot at sequence 20, followed by 5 WAL records.
        recovered = self.restart_cache(snapshot_after=10)

        self.assertEqual(recovered.seq, 25)
        self.assertEqual(len(recovered.cache), 25)

        for i in range(1, 26):
            self.assertEqual(recovered.get(i), i * 10)

    # -----------------------------------------
    # Snapshot exists but WAL was not rotated
    # -----------------------------------------

    def test_snapshot_without_rotation(self):
        cache = self.new_cache(snapshot_after=1000)

        for i in range(1, 11):
            cache.put(i, i * 10)

        # Simulate a crash after snapshot persistence
        # but before WAL rotation.
        cache.snapshot.save({
            "seq": cache.seq,
            "cache": list(cache.cache.items())
        })

        recovered = self.restart_cache(snapshot_after=1000)

        # WAL records are already included in the snapshot.
        self.assertEqual(recovered.seq, 10)
        self.assertEqual(len(recovered.cache), 10)

        for i in range(1, 11):
            self.assertEqual(recovered.get(i), i * 10)

    # -----------------------------------------
    # LRU eviction survives recovery
    # -----------------------------------------

    def test_eviction_survives_recovery(self):
        cache = self.new_cache(capacity=3, snapshot_after=100)

        cache.put(1, 100)
        cache.put(2, 200)
        cache.put(3, 300)

        cache.get(1)
        cache.put(4, 400)

        self.assertEqual(cache.get(2), -1)

        recovered = self.restart_cache(
            capacity=3,
            snapshot_after=100
        )

        # Recovery reconstructs ordering from PUT operations only.
        self.assertEqual(recovered.get(1), -1)
        self.assertEqual(recovered.get(2), 200)
        self.assertEqual(recovered.get(3), 300)
        self.assertEqual(recovered.get(4), 400)


    # -----------------------------------------
    # Sequence numbers survive recovery
    # -----------------------------------------

    def test_sequence_continuity(self):
        cache = self.new_cache(snapshot_after=100)

        for i in range(10):
            cache.put(i, i * 10)

        self.assertEqual(cache.seq, 10)

        recovered = self.restart_cache(snapshot_after=100)

        self.assertEqual(recovered.seq, 10)

        recovered.put(100, 1000)

        self.assertEqual(recovered.seq, 11)

        final_cache = self.restart_cache(snapshot_after=100)

        self.assertEqual(final_cache.get(100), 1000)
        self.assertEqual(final_cache.seq, 11)

    # -----------------------------------------
    # Concurrent reads and writes
    # -----------------------------------------

    def test_concurrent_access(self):
        thread_count = 6
        operations_per_thread = 30

        cache = self.new_cache(
            capacity=1000,
            snapshot_after=10
        )

        errors = []
        errors_lock = threading.Lock()
        barrier = threading.Barrier(thread_count)

        def worker(thread_id):
            try:
                barrier.wait(timeout=10)

                for i in range(operations_per_thread):
                    key = thread_id * 1000 + i
                    value = key * 10

                    cache.put(key, value)

                    result = cache.get(key)

                    if result != value:
                        raise AssertionError(
                            f"Key {key}: expected {value}, got {result}"
                        )

            except Exception as exc:
                with errors_lock:
                    errors.append(exc)

        threads = [
            threading.Thread(target=worker, args=(i,))
            for i in range(thread_count)
        ]

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join(timeout=30)

        for thread in threads:
            self.assertFalse(thread.is_alive(), "Worker thread hung")

        self.assertEqual(errors, [])

        expected_count = thread_count * operations_per_thread

        self.assertEqual(len(cache.cache), expected_count)
        self.assertEqual(cache.seq, expected_count)

        # Verify every key is still present.
        for thread_id in range(thread_count):
            for i in range(operations_per_thread):
                key = thread_id * 1000 + i
                self.assertEqual(cache.get(key), key * 10)

    # -----------------------------------------
    # Concurrent writes followed by recovery
    # -----------------------------------------

    def test_concurrent_recovery(self):
        thread_count = 4
        operations_per_thread = 25

        cache = self.new_cache(
            capacity=1000,
            snapshot_after=10
        )

        errors = []
        errors_lock = threading.Lock()
        barrier = threading.Barrier(thread_count)

        def worker(thread_id):
            try:
                barrier.wait(timeout=10)

                for i in range(operations_per_thread):
                    key = thread_id * 1000 + i
                    cache.put(key, key + 500)

            except Exception as exc:
                with errors_lock:
                    errors.append(exc)

        threads = [
            threading.Thread(target=worker, args=(i,))
            for i in range(thread_count)
        ]

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join(timeout=30)

        for thread in threads:
            self.assertFalse(thread.is_alive(), "Worker thread hung")

        self.assertEqual(errors, [])

        expected_count = thread_count * operations_per_thread

        # Validate state before restart.
        self.assertEqual(cache.seq, expected_count)
        self.assertEqual(len(cache.cache), expected_count)

        # Simulate restart.
        recovered = self.restart_cache(
            capacity=1000,
            snapshot_after=10
        )

        self.assertEqual(recovered.seq, expected_count)
        self.assertEqual(len(recovered.cache), expected_count)

        for thread_id in range(thread_count):
            for i in range(operations_per_thread):
                key = thread_id * 1000 + i

                self.assertEqual(
                    recovered.get(key),
                    key + 500
                )

    # -----------------------------------------
    # Multiple snapshots and restarts
    # -----------------------------------------

    def test_multiple_restarts(self):
        cache = self.new_cache(snapshot_after=5)

        for i in range(1, 8):
            cache.put(i, i * 10)

        recovered = self.restart_cache(snapshot_after=5)

        for i in range(8, 16):
            recovered.put(i, i * 10)

        self.assertEqual(recovered.seq, 15)

        final_cache = self.restart_cache(snapshot_after=5)

        self.assertEqual(final_cache.seq, 15)
        self.assertEqual(len(final_cache.cache), 15)

        for i in range(1, 16):
            self.assertEqual(final_cache.get(i), i * 10)


if __name__ == "__main__":
    unittest.main(verbosity=2)

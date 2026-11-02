import json
import zlib
import struct
import os

HEADER_FORMAT = '!II'
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)

class WAL:
    def __init__(self, path):
        self.path = path
        self.f = open(path, "ab")

    def append(self, data):
        payload = json.dumps(data).encode("utf-8")
        self.f.write(struct.pack(HEADER_FORMAT, zlib.crc32(payload), len(payload)) + payload)
        self.f.flush()
        os.fsync(self.f.fileno())

    def replay(self):
        with open(self.path, "rb") as file:
            while True:
                header = file.read(HEADER_SIZE)
                if len(header) != HEADER_SIZE:
                    return
                checksum, length = struct.unpack(HEADER_FORMAT, header)
                payload = file.read(length)
                if len(payload) != length or zlib.crc32(payload) != checksum:
                    return

                yield json.loads(payload)

    def rotate(self):
        self.close()
        os.replace(self.path, self.path + ".old")
        self.f = open(self.path, "ab")
        os.remove(self.path + ".old")

    def close(self):
        if not self.f.closed:
            self.f.flush()
            os.fsync(self.f.fileno())
            self.f.close()
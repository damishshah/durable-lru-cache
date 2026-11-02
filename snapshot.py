import json
import os

class Snapshot:
    def __init__(self, path):
        self.path = path

    def save(self, data):
        tmp_path = self.path + ".tmp"
        with open(tmp_path, "w") as file:
            json.dump(data, file)
            file.flush()
            os.fsync(file.fileno())
        os.replace(tmp_path, self.path)

    def load(self):
        with open(self.path, "r") as file:
            return json.load(file)
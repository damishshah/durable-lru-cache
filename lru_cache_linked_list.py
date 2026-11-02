class Node:
    def __init__(self, key, value=None):
        self.key = key
        self.value = value
        self.prev = None
        self.next = None


class DoublyLinkedList:
    def __init__(self):
        self.head = Node(None)
        self.tail = Node(None)

        self.head.next = self.tail
        self.tail.prev = self.head

    def push(self, node):
        node.prev = self.head
        node.next = self.head.next

        self.head.next.prev = node
        self.head.next = node

    def delete(self, node):
        node.prev.next = node.next
        node.next.prev = node.prev

    def move_to_end(self, node):
        self.delete(node)
        self.push(node)

    def pop(self):
        if self.tail.prev == self.head:
            return None

        node = self.tail.prev
        self.delete(node)
        return node


class LRUCache:
    def __init__(self, capacity: int):
        self.capacity = capacity
        self.cache = {}
        self.list = DoublyLinkedList()

    def get(self, key: int) -> int:
        if key not in self.cache:
            return -1

        node = self.cache[key]
        self.list.move_head(node)
        return node.value

    def put(self, key: int, value: int) -> None:
        if key in self.cache:
            node = self.cache[key]
            node.value = value
            self.list.move_head(node)
        else:
            node = Node(key, value)
            self.cache[key] = node
            self.list.push(node)

        if len(self.cache) > self.capacity:
            node = self.list.pop()
            del self.cache[node.key]
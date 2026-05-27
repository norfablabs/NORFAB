import threading

from norfab.core import NFP
from norfab.core.broker import NFPBroker


class DummySocket:
    def __init__(self):
        self.sent = []

    def send_multipart(self, msg):
        self.sent.append(msg)


def make_broker():
    broker = NFPBroker.__new__(NFPBroker)
    broker.socket = DummySocket()
    broker.socket_lock = threading.Lock()
    broker.multiplier = 6
    broker.keepalive = 2500
    broker.workers = {}
    broker.services = {}
    broker.build_message = NFP.MessageBuilder()
    return broker


def test_require_worker_handles_binary_address():
    broker = make_broker()
    address = b"\x00\x80worker"

    worker = broker.require_worker(address)

    assert worker.address == address
    assert broker.workers[address] is worker

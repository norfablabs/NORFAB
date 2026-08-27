import threading
import time

import pytest

from norfab.core import NFP
from norfab.core.broker import NFPBroker, NFPService
from norfab.core.keepalives import KeepAliver

pytestmark = pytest.mark.core


class DummySocket:
    def __init__(self) -> None:
        self.sent = []

    def send_multipart(self, msg: list) -> None:
        self.sent.append(msg)


def make_broker() -> NFPBroker:
    broker = NFPBroker.__new__(NFPBroker)
    broker.socket = DummySocket()
    broker.multiplier = 6
    broker.keepalive = 2500
    broker.workers = {}
    broker.services = {}
    broker.build_message = NFP.MessageBuilder()
    return broker


def test_require_worker_handles_binary_address() -> None:
    broker = make_broker()
    address = b"\x00\x80worker"

    worker = broker.require_worker(address)

    assert worker.address == address
    assert broker.workers[address] is worker


def test_broker_sends_due_keepalives_from_mediate_loop() -> None:
    broker = make_broker()
    worker = broker.require_worker(b"worker-1")
    worker.service = NFPService(b"service-1")
    worker.ready = True
    worker.start_keepalives()
    worker.keepaliver.keepalive_at = time.time() - 1

    broker.send_due_keepalives()

    assert len(broker.socket.sent) == 1
    assert broker.socket.sent[0][0] == b"worker-1"
    assert broker.socket.sent[0][2] == NFP.BROKER
    assert broker.socket.sent[0][3] == NFP.KEEPALIVE
    assert worker.keepaliver.keepalives_send == 1


def test_keepaliver_start_does_not_create_socket_thread() -> None:
    keepaliver = KeepAliver(
        address=b"worker-1",
        multiplier=6,
        keepalive=2500,
        exit_event=threading.Event(),
        service=b"service-1",
        whoami=NFP.BROKER,
        name="NFPBroker",
    )

    keepaliver.start()

    assert not hasattr(keepaliver, "keepalive_thread")

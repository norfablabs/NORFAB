from typing import List

"""NORFAB Protocol definitions"""

# This is the version of NFP/Client we implement
CLIENT = b"NFPC01"

# This is the version of NFP/Worker we implement
WORKER = b"NFPW01"

# This is the version of NFP/Broker we implement
BROKER = b"NFPB01"

# NORFAB Protocol commands, as strings
OPEN = b"0x00"
READY = b"0x01"
KEEPALIVE = b"0x02"
DISCONNECT = b"0x03"
POST = b"0x04"
RESPONSE = b"0x05"
GET = b"0x06"
DELETE = b"0x07"
EVENT = b"0x08"

commands = [
    b"OPEN",
    b"READY",
    b"KEEPALIVE",
    b"DISCONNECT",
    b"POST",
    b"RESPONSE",
    b"GET",
    b"DELETE",
    b"EVENT",
]

client_commands = [OPEN, DISCONNECT, POST, GET, DELETE]

worker_commands = [OPEN, READY, KEEPALIVE, DISCONNECT, RESPONSE]

broker_commands = [OPEN, KEEPALIVE, DISCONNECT, POST, RESPONSE, GET, DELETE]

# Convenience constants for frame counts
FRAME_COUNTS = {
    "broker_to_worker": 8,  # address, empty, header, command, sender, empty, uuid, data
    "client_to_broker": 7,  # empty, header, command, service, workers, uuid, request
    "worker_ready": 4,  # empty, header, command, service
    "worker_response_min": 3,  # empty, header, command + response data
}


class MessageBuilder:
    """Builder class for constructing NFP protocol messages."""

    @staticmethod
    def broker_to_worker_post(
        worker_address: bytes, sender: bytes, uuid: bytes, data: bytes
    ) -> List[bytes]:
        """Build a POST message from broker to worker."""
        return [worker_address, b"", WORKER, POST, sender, b"", uuid, data]

    @staticmethod
    def broker_to_worker_get(
        worker_address: bytes, sender: bytes, uuid: bytes, data: bytes
    ) -> List[bytes]:
        """Build a GET message from broker to worker."""
        return [worker_address, b"", WORKER, GET, sender, b"", uuid, data]

    @staticmethod
    def broker_to_worker_disconnect(
        worker_address: bytes,
        service: bytes,
    ) -> List[bytes]:
        """Build a DISCONNECT message from broker to worker."""
        return [worker_address, b"", WORKER, service, DISCONNECT]

    @staticmethod
    def worker_to_broker_ready(service: bytes) -> List[bytes]:
        """Build READY message from worker to broker."""
        return [b"", WORKER, READY, service]

    @staticmethod
    def worker_to_broker_disconnect(service: bytes) -> List[bytes]:
        """Build DISCONNECT message from worker to broker."""
        return [b"", WORKER, DISCONNECT, service]

    @staticmethod
    def worker_to_broker_response(response_data: List[bytes]) -> List[bytes]:
        """Build RESPONSE message from worker to broker."""
        return [b"", WORKER, RESPONSE] + response_data

    @staticmethod
    def worker_to_broker_event(event_data: List[bytes]) -> List[bytes]:
        """Build EVENT message from worker to broker."""
        return [b"", WORKER, EVENT] + event_data

    @staticmethod
    def worker_to_broker_keepalive(service: bytes) -> List[bytes]:
        """Build KEEPALIVE message from worker to broker."""
        return [b"", WORKER, KEEPALIVE, service]

    @staticmethod
    def broker_to_worker_keepalive(address: bytes, service: bytes) -> List[bytes]:
        """Build KEEPALIVE message from broker to worker."""
        return [address, b"", BROKER, KEEPALIVE, service]

    @staticmethod
    def client_to_broker_post(
        command: bytes, service: bytes, workers: bytes, uuid: bytes, request: bytes
    ) -> List[bytes]:
        """Build a POST message from client to broker."""
        return [b"", CLIENT, POST, service, workers, uuid, request]

    @staticmethod
    def client_to_broker_get(
        command: bytes, service: bytes, workers: bytes, uuid: bytes, request: bytes
    ) -> List[bytes]:
        """Build a GET message from client to broker."""
        return [b"", CLIENT, GET, service, workers, uuid, request]

    @staticmethod
    def broker_to_client_response(
        client: bytes, service: bytes, message: List[bytes]
    ) -> List[bytes]:
        """Build RESPONSE message from broker to client."""
        return [client, b"", CLIENT, RESPONSE, service] + message

    @staticmethod
    def broker_to_client_event(
        client: bytes, service: bytes, message: List[bytes]
    ) -> List[bytes]:
        """Build EVENT message from broker to client."""
        return [client, b"", CLIENT, EVENT, service] + message

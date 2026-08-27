import logging
import threading
import time

from . import NFP

log = logging.getLogger(__name__)


class KeepAliver:
    """
    Helper class to track keepalives between Broker and Workers in a consistent way.

    Args:
        address (str): Optional address to send keepalives to.
        multiplier (int): Number of keepalives before considered dead.
        keepalive (int): Interval between keepalives in milliseconds.
        exit_event (threading.Event): Global exit event signaled by NFAPI if set, stop sending keepalives.
        service (str): Name of the service to include in keepalives.
        whoami (str): Identifier e.g. NFP.WORKER or NFP.BROKER to use as keepalives header.
        name (str): Descriptive name to include in logs.

    Attributes:
        address (str): Address to send keepalives to.
        exit_event (threading.Event): Global exit event.
        destroy_event (threading.Event): Event used by worker to stop keepalives.
        keepalive (int): Interval between keepalives in milliseconds.
        multiplier (int): Number of keepalives before considered dead.
        service (str): Name of the service to include in keepalives.
        whoami (str): Identifier to use as keepalives header.
        name (str): Descriptive name to include in logs.
        started_at (float): Timestamp when keepalives started.
        keepalives_received (int): Number of keepalives received.
        keepalives_send (int): Number of keepalives sent.
        holdtime (float): Expiry time unless heartbeat is received.
        keepalive_at (float): Time to send the next keepalive.

    Methods:
        start(): Start keepalive tracking.
        stop(): Stop keepalive tracking.
        due(): Check if a heartbeat is due.
        make_message(): Build the heartbeat message and update counters.
        received_heartbeat(msg): Update holdtime when a heartbeat is received.
        restart(): Restart keepalive timers.
        is_alive(): Check if the other party is seen before expiry.
        show_holdtime(): Show remaining holdtime.
        show_alive_for(): Show duration since keepalives started.
    """

    def __init__(
        self,
        address: str,
        multiplier: int,  # e.g. 6 times
        keepalive: int,  # e.g. 5000 ms
        exit_event: threading.Event,
        service: str,
        whoami: str,  # NFP.BROKER or NFP.WORKER
        name: str,
    ) -> None:
        self.address = address
        self.exit_event = exit_event or threading.Event()
        self.destroy_event = (
            threading.Event()
        )  # destroy event, used by worker to stop keepalives
        self.keepalive = keepalive
        self.multiplier = multiplier
        self.service = service
        self.whoami = whoami
        self.name = f"{name}-keepaliver"
        self.build_message = NFP.MessageBuilder()

        self.started_at = 0
        self.keepalives_received = 0
        self.keepalives_send = 0
        self.holdtime = (
            time.time() + 0.001 * self.multiplier * self.keepalive
        )  # expires at this point, unless heartbeat
        self.keepalive_at = (
            time.time() + 0.001 * self.keepalive
        )  # when to send keepalive

    def start(self) -> bool:
        """
        Start keepalive tracking and record the start time.

        Returns:
            bool: True if keepalive tracking was successfully started.
        """
        self.started_at = time.time()
        return True

    def stop(self) -> bool:
        """
        Stops keepalive tracking by setting the destroy event.

        Returns:
            bool: True if keepalive tracking was successfully stopped.
        """
        if not self.destroy_event.is_set():
            self.destroy_event.set()
        return True

    def due(self) -> bool:
        """
        Check if a heartbeat should be sent.
        """
        return (
            not self.exit_event.is_set()
            and not self.destroy_event.is_set()
            and time.time() > self.keepalive_at
        )

    def make_message(self) -> list:
        """
        Build a heartbeat message and update keepalive send counters.
        """
        if self.whoami == NFP.WORKER:
            msg = self.build_message.worker_to_broker_keepalive(service=self.service)
        elif self.whoami == NFP.BROKER:
            msg = self.build_message.broker_to_worker_keepalive(
                address=self.address,
                service=self.service,
            )
        else:
            raise ValueError(f"Unsupported keepalive identity: {self.whoami}")

        self.keepalive_at = time.time() + 0.001 * self.keepalive
        self.keepalives_send += 1
        log.debug(f"{self.name} - send keepalive '{msg}'")
        return msg

    def received_heartbeat(self, msg) -> None:
        """
        Handles the reception of a heartbeat message from another party.

        This method updates the holdtime and increments the count of received keepalives.

        Args:
            msg (str): The heartbeat message received.
        """
        log.debug(f"{self.name} - received keepalive '{msg}'")
        self.keepalives_received += 1
        self.holdtime = time.time() + 0.001 * self.multiplier * self.keepalive

    def restart(self) -> None:
        """
        Restart keepalive timers.

        This method resets the counters for received and sent keepalives, sets
        the start time to the current time, and calculates the holdtime and the
        next keepalive time based on the configured interval and multiplier.

        """
        self.destroy_event.clear()
        self.keepalives_received = 0
        self.keepalives_send = 0
        self.started_at = time.time()
        self.holdtime = (
            time.time() + 0.001 * self.multiplier * self.keepalive
        )  # expires at this point, unless heartbeat
        self.keepalive_at = (
            time.time() + 0.001 * self.keepalive
        )  # when to send keepalive

    def is_alive(self) -> bool:
        """
        Check if the other party is still alive based on the hold time.

        Returns:
            bool: True if the other party has been seen before the hold time expires, False otherwise.
        """
        return self.holdtime > time.time()

    def show_holdtime(self) -> float:
        """
        Calculate and return the remaining hold time.

        This method subtracts the current time from the holdtime attribute
        and rounds the result to one decimal place.

        Returns:
            float: The remaining hold time in seconds, rounded to one decimal place.
        """
        return round(self.holdtime - time.time(), 1)

    def show_alive_for(self) -> int:
        """
        Calculate the duration for which the instance has been alive.

        Returns:
            int: The number of seconds since the instance was started.
        """
        return int(time.time() - self.started_at)

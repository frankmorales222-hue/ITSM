import threading
import time


class Scheduler:
    def __init__(self, full_action, heartbeat_action, full_interval: int, heartbeat_interval: int, refresh_requested=None):
        self.full_action = full_action
        self.heartbeat_action = heartbeat_action
        self.full_interval = max(300, full_interval)
        self.heartbeat_interval = max(15, heartbeat_interval)
        self.refresh_requested = refresh_requested
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, name="northstar-agent-scheduler", daemon=True)

    def start(self) -> None:
        self.thread.start()

    def _run(self) -> None:
        next_full = 0.0
        next_heartbeat = 0.0
        while not self.stop_event.is_set():
            current = time.monotonic()
            if self.refresh_requested and self.refresh_requested():
                try:
                    self.heartbeat_action()
                finally:
                    next_heartbeat = time.monotonic() + self.heartbeat_interval
            if current >= next_full:
                try:
                    self.full_action()
                finally:
                    next_full = time.monotonic() + self.full_interval
            if current >= next_heartbeat:
                try:
                    self.heartbeat_action()
                finally:
                    next_heartbeat = time.monotonic() + self.heartbeat_interval
            self.stop_event.wait(2)

    def stop(self) -> None:
        self.stop_event.set()
        self.thread.join(timeout=15)

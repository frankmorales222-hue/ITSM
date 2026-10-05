import threading
import time


class Scheduler:
    def __init__(self, full_action, heartbeat_action, full_interval: int, heartbeat_interval: int,
                 refresh_requested=None, full_timeout: int = 900, full_timeout_action=None,
                 maintenance_action=None, maintenance_interval: int = 21600):
        self.full_action = full_action
        self.heartbeat_action = heartbeat_action
        self.full_interval = max(300, full_interval)
        self.heartbeat_interval = min(30, max(15, heartbeat_interval))
        self.refresh_requested = refresh_requested
        self.full_timeout = max(1, full_timeout)
        self.full_timeout_action = full_timeout_action
        self.maintenance_action = maintenance_action
        self.maintenance_interval = max(3600, maintenance_interval)
        self.stop_event = threading.Event()
        self.inventory_thread = threading.Thread(
            target=self._run_inventory, name="northstar-agent-inventory-scheduler", daemon=True
        )
        self.action_thread = threading.Thread(
            target=self._run_actions, name="northstar-agent-action-scheduler", daemon=True
        )
        self.maintenance_thread = threading.Thread(
            target=self._run_maintenance, name="northstar-agent-maintenance", daemon=True
        ) if maintenance_action else None

    def start(self) -> None:
        self.inventory_thread.start()
        self.action_thread.start()
        if self.maintenance_thread:
            self.maintenance_thread.start()

    def _run_inventory(self) -> None:
        next_full = 0.0
        while not self.stop_event.is_set():
            current = time.monotonic()
            if current >= next_full:
                runner = threading.Thread(
                    target=self.full_action, name="northstar-agent-inventory-run", daemon=True
                )
                runner.start()
                runner.join(timeout=self.full_timeout)
                if runner.is_alive() and self.full_timeout_action:
                    self.full_timeout_action()
                next_full = time.monotonic() + self.full_interval
            self.stop_event.wait(2)

    def _run_actions(self) -> None:
        next_heartbeat = 0.0
        while not self.stop_event.is_set():
            current = time.monotonic()
            refresh = self.refresh_requested and self.refresh_requested()
            if refresh or current >= next_heartbeat:
                try:
                    self.heartbeat_action()
                finally:
                    next_heartbeat = time.monotonic() + self.heartbeat_interval
            self.stop_event.wait(2)

    def _run_maintenance(self) -> None:
        next_run = 0.0
        while not self.stop_event.is_set():
            if time.monotonic() >= next_run:
                try:
                    self.maintenance_action()
                except Exception:
                    # Maintenance is best effort. The action itself records
                    # details; an unexpected failure must not end future runs.
                    pass
                finally:
                    next_run = time.monotonic() + self.maintenance_interval
            self.stop_event.wait(5)

    def stop(self) -> None:
        self.stop_event.set()
        self.inventory_thread.join(timeout=15)
        self.action_thread.join(timeout=15)
        if self.maintenance_thread:
            self.maintenance_thread.join(timeout=15)

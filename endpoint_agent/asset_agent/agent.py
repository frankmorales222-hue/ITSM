import argparse
import hashlib
import json
import os
import signal
import re
import subprocess
import time
import sys
import threading
from pathlib import Path

from . import __version__
from .config import AgentConfig, default_data_dir
from .diagnostics.logger import configure_logging, event
from .identity.device_identity import collect_identity
from .inventory.collector import collect_full_inventory
from .observed_user import observed_user_claims
from .scheduler import Scheduler
from .storage.database import AgentDatabase
from .transport.sync_interface import InventoryTransport


class SingleInstance:
    """Hold a non-blocking Windows file lock for the long-running agent."""
    def __init__(self, path: Path):
        self.path = path
        self.handle = None

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = open(self.path, "a+b")
        if self.handle.tell() == 0:
            self.handle.write(b"0")
            self.handle.flush()
        self.handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            self.handle.close()
            self.handle = None
            return False

    def release(self) -> None:
        if not self.handle:
            return
        try:
            if os.name == "nt":
                import msvcrt
                self.handle.seek(0)
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
        finally:
            self.handle.close()
            self.handle = None


class Agent:
    def __init__(self, config: AgentConfig, data_dir: Path):
        self.config = config
        self.data_dir = data_dir
        self.database = AgentDatabase(data_dir / "agent.db")
        self.transport = InventoryTransport(config.server_url, tls_certificate_sha256=config.tls_certificate_sha256)
        self.logger = configure_logging(data_dir / "agent.log")

    def enroll(self, enrollment_token: str) -> dict:
        identity = collect_identity()
        result = self.transport.enroll(enrollment_token, identity["device_id"], identity["hostname"], __version__)
        self.config.set_credential(result["credential"])
        self.config.save(self.data_dir / "config.json")
        event(self.logger, "AGENT_ENROLLED", agent_id=result["agent_id"], device_id_suffix=identity["device_id"][-8:])
        return result

    def flush(self, strict: bool = False) -> None:
        if not self.config.credential:
            return
        for item in self.database.pending():
            try:
                self.transport.upload(self.config.credential, json.loads(item["payload"]))
                self.database.delivered(item["id"])
                event(self.logger, "INVENTORY_SYNC_COMPLETED", outbox_id=item["id"])
            except Exception as exc:
                self.database.failed(item["id"], str(exc))
                event(self.logger, "INVENTORY_SYNC_FAILED", exception_type=type(exc).__name__, error=str(exc))
                if strict:
                    raise
                break

    def collect_and_sync(self, strict: bool = False) -> dict:
        event(self.logger, "DEVICE_INVENTORY_STARTED")
        inventory = collect_full_inventory(observed_user_claims(self.config.user_email_override))
        self.database.save_inventory(inventory)
        event(self.logger, "DEVICE_INVENTORY_COMPLETED", unknown_count=inventory["health"]["unknown_count"])
        self.flush(strict=strict)
        return inventory

    def heartbeat(self) -> None:
        if not self.config.credential:
            return
        try:
            identity = collect_identity()
            claims = observed_user_claims(self.config.user_email_override)
            result = self.transport.heartbeat(self.config.credential, {"hostname": identity["hostname"],
                                     "agent_version": __version__, "observed_user_email": claims.get("email"),
                                     "observed_user": claims})
            alerts = result.get("alerts", []) if isinstance(result, dict) else []
            tray_signal_directory = self.data_dir / "tray"
            tray_signal_directory.mkdir(parents=True, exist_ok=True)
            (tray_signal_directory / "alerts.json").write_text(json.dumps({"alerts": alerts}), encoding="utf-8")
            if isinstance(result, dict):
                self.schedule_agent_update(result.get("agent_update"))
        except Exception as exc:
            event(self.logger, "AGENT_HEARTBEAT_FAILED", exception_type=type(exc).__name__, error=str(exc))
        # A transient desktop-notification, update, or heartbeat error must
        # never prevent a previously approved remediation action from running.
        try:
            self.perform_approved_action()
        except Exception as exc:
            event(self.logger, "ENDPOINT_ACTION_EXECUTION_FAILED", exception_type=type(exc).__name__, error=str(exc))

    def consume_tray_refresh_request(self) -> bool:
        request_path = self.data_dir / "tray" / "refresh.request"
        if not request_path.is_file():
            return False
        try:
            request_path.unlink()
            event(self.logger, "TRAY_REFRESH_REQUESTED")
            return True
        except OSError:
            return False

    @staticmethod
    def _version_tuple(value: object) -> tuple[int, int, int] | None:
        pieces = str(value or "").strip().split(".")
        if len(pieces) != 3 or any(not part.isdigit() for part in pieces):
            return None
        return tuple(map(int, pieces))

    def schedule_agent_update(self, update: object) -> None:
        """Silently install a newer, server-supplied and hash-verified agent.

        The endpoint credential is used only for the authenticated download.
        The update state records a version and checksum, never tickets,
        credentials, or user content.  A failed update is not retried in a
        tight loop; a later package/version can safely replace it.
        """
        if not isinstance(update, dict):
            return
        target_version = self._version_tuple(update.get("version"))
        current_version = self._version_tuple(__version__)
        digest = str(update.get("sha256") or "").lower()
        download_path = str(update.get("download_path") or "")
        if (not target_version or not current_version or target_version <= current_version or
                len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest) or
                download_path != "/api/agent/update/download"):
            return
        updates_dir = self.data_dir / "updates"
        updates_dir.mkdir(parents=True, exist_ok=True)
        state_path = updates_dir / "update-state.json"
        try:
            previous = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
        except (OSError, ValueError):
            previous = {}
        if previous.get("version") == ".".join(map(str, target_version)) and previous.get("status") in {"scheduled", "failed"}:
            return
        target = updates_dir / f"NorthstarEndpointAgent-Setup-{'.'.join(map(str, target_version))}.exe"
        try:
            if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest().lower() != digest:
                target.unlink(missing_ok=True)
                self.transport.download(download_path, self.config.credential, target)
            if hashlib.sha256(target.read_bytes()).hexdigest().lower() != digest:
                target.unlink(missing_ok=True)
                raise RuntimeError("downloaded agent update failed checksum validation")
            state_path.write_text(json.dumps({"version": ".".join(map(str, target_version)),
                                               "sha256": digest, "status": "scheduled"}), encoding="utf-8")
            # Run a separate command process.  Setup stops this scheduled agent
            # before replacing its files, so it must not depend on this process
            # remaining alive after the installer starts.
            command = f'ping 127.0.0.1 -n 6 > nul & start "" /wait "{target}" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /AUTOUPDATE'
            subprocess.Popen(["cmd.exe", "/c", command], close_fds=True,
                             creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) |
                                           getattr(subprocess, "DETACHED_PROCESS", 0))
            event(self.logger, "AGENT_UPDATE_SCHEDULED", version=".".join(map(str, target_version)))
        except Exception as exc:
            state_path.write_text(json.dumps({"version": ".".join(map(str, target_version)),
                                               "sha256": digest, "status": "failed"}), encoding="utf-8")
            event(self.logger, "AGENT_UPDATE_FAILED", exception_type=type(exc).__name__)

    @staticmethod
    def _run(command: list[str], timeout: int = 30) -> tuple[bool, str]:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout,
                                   shell=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        output = (completed.stdout or completed.stderr or "").strip()
        return completed.returncode == 0, output[-900:]

    def perform_approved_action(self) -> None:
        try:
            result = self.transport.next_action(self.config.credential)
        except Exception as exc:
            event(self.logger, "ENDPOINT_ACTION_POLL_FAILED", exception_type=type(exc).__name__, error=str(exc))
            return
        action = result.get("action") if isinstance(result, dict) else None
        if not action:
            return
        action_id = int(action["id"])
        action_type = str(action.get("action_type") or "")
        target = str(action.get("target") or "").strip()
        succeeded = False
        summary = "Unsupported endpoint action"
        try:
            if action_type == "terminate_process":
                # Accept an executable name (or a pasted Windows path), but
                # always reduce it to a basename before invoking taskkill.
                # This prevents shell/path injection and matches taskkill's
                # /IM contract, which accepts an image name only.
                image_name = os.path.basename(target.strip().strip('"'))
                if not re.fullmatch(r"[A-Za-z0-9_. -]{1,120}\.exe", image_name, flags=re.IGNORECASE):
                    raise ValueError("Application name is not allowed")
                taskkill = os.path.join(os.environ.get("SystemRoot", r"C:\\Windows"), "System32", "taskkill.exe")
                if not os.path.isfile(taskkill):
                    taskkill = "taskkill.exe"
                succeeded, detail = self._run([taskkill, "/F", "/T", "/IM", image_name], 20)
                summary = detail or (f"Closed {image_name}." if succeeded else f"Could not close {image_name}.")
            elif action_type == "restart_service":
                if not re.fullmatch(r"[A-Za-z0-9_.-]{1,120}", target):
                    raise ValueError("Service name is not allowed")
                stopped, stop_detail = self._run(["sc.exe", "stop", target], 30)
                if not stopped and "service has not been started" not in stop_detail.lower():
                    raise RuntimeError(stop_detail or f"Could not stop service {target}.")
                for _ in range(15):
                    _queried, state = self._run(["sc.exe", "query", target], 10)
                    if "STOPPED" in state.upper():
                        break
                    time.sleep(1)
                else:
                    raise RuntimeError(f"Service {target} did not stop within 15 seconds.")
                succeeded, detail = self._run(["sc.exe", "start", target], 30)
                summary = detail or (f"Restarted service {target}." if succeeded else f"Could not restart service {target}.")
        except Exception as exc:
            summary = f"{type(exc).__name__}: {exc}"
        try:
            self.transport.action_result(self.config.credential, action_id, succeeded, summary)
            event(self.logger, "ENDPOINT_ACTION_COMPLETED", action_id=action_id,
                  action_type=action_type, succeeded=succeeded, summary=summary)
        except Exception as exc:
            event(self.logger, "ENDPOINT_ACTION_RESULT_FAILED", action_id=action_id,
                  exception_type=type(exc).__name__, error=str(exc), summary=summary)

    def close(self) -> None:
        self.database.close()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Northstar Windows endpoint inventory agent")
    parser.add_argument("--data-dir", type=Path, default=default_data_dir())
    parser.add_argument("--server")
    parser.add_argument("--enrollment-token")
    parser.add_argument("--enrollment-token-file", type=Path)
    parser.add_argument("--user-email", default="")
    parser.add_argument("--credential-scope", choices=("user", "machine"), default="")
    parser.add_argument("--tls-pin", default="")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)
    config_path = args.data_dir / "config.json"
    config = AgentConfig.load(config_path) if config_path.exists() else AgentConfig(server_url=args.server or "")
    if args.server:
        config.server_url = args.server
    if args.user_email:
        config.user_email_override = args.user_email
    if args.credential_scope:
        config.credential_scope = args.credential_scope
    if args.tls_pin:
        config.tls_certificate_sha256 = args.tls_pin.strip().lower()
    if not config.server_url:
        parser.error("--server is required for initial configuration")
    # Persist the notification-ready heartbeat rate when loading an earlier
    # installation so later launches do not silently restore the old cadence.
    if config_path.exists():
        config.save(config_path)
    instance = None if args.once else SingleInstance(args.data_dir / "agent.lock")
    if instance and not instance.acquire():
        return 0
    agent = Agent(config, args.data_dir)
    try:
        enrollment_token = args.enrollment_token
        if args.enrollment_token_file:
            enrollment_token = args.enrollment_token_file.read_text(encoding="utf-8").strip()
            args.enrollment_token_file.unlink(missing_ok=True)
        if enrollment_token:
            agent.enroll(enrollment_token)
        if not config.credential:
            parser.error("agent is not enrolled; provide --enrollment-token")
        if args.once:
            agent.collect_and_sync(strict=True)
            return 0
        event(agent.logger, "AGENT_STARTED", version=__version__)
        scheduler = Scheduler(agent.collect_and_sync, agent.heartbeat,
                              config.full_interval_seconds, config.heartbeat_interval_seconds,
                              refresh_requested=agent.consume_tray_refresh_request)
        scheduler.start()
        stop = threading.Event()
        signal.signal(signal.SIGINT, lambda *_: stop.set())
        signal.signal(signal.SIGTERM, lambda *_: stop.set())
        stop.wait()
        scheduler.stop()
        event(agent.logger, "AGENT_STOPPED")
        return 0
    finally:
        agent.close()
        if instance:
            instance.release()


if __name__ == "__main__":
    raise SystemExit(main())

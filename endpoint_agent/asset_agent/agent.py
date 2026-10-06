import argparse
import ctypes
from ctypes import wintypes
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
from datetime import datetime, timezone, timedelta

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
        self._last_heartbeat_ok_log = 0.0
        self._action_worker = None
        self._action_started_at = 0.0
        self._action_current = None
        self._action_timeout_reported = False
        self._action_lock = threading.Lock()

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

    def _state_file(self, relative: str) -> dict:
        try:
            value = json.loads((self.data_dir / relative).read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    def heartbeat(self, strict: bool = False, perform_actions: bool = True) -> None:
        if not self.config.credential:
            return
        try:
            update_state = self._state_file("updates/update-state.json")
            reported_update = self._version_tuple(update_state.get("version"))
            current_version = self._version_tuple(__version__)
            if (update_state.get("status") == "scheduled" and reported_update and current_version and
                    reported_update <= current_version):
                update_state["status"] = "installed"
                update_state["completed_at"] = datetime.now(timezone.utc).isoformat()
                try:
                    (self.data_dir / "updates/update-state.json").write_text(
                        json.dumps(update_state), encoding="utf-8")
                except OSError:
                    pass
            identity = collect_identity()
            claims = observed_user_claims(self.config.user_email_override)
            result = self.transport.heartbeat(self.config.credential, {"hostname": identity["hostname"],
                                     "agent_version": __version__, "observed_user_email": claims.get("email"),
                                     "observed_user": claims,
                                     "update_state": update_state,
                                     "self_repair": self._state_file("self-repair-state.json")})
            alerts = result.get("alerts", []) if isinstance(result, dict) else []
            tray_signal_directory = self.data_dir / "tray"
            tray_signal_directory.mkdir(parents=True, exist_ok=True)
            (tray_signal_directory / "alerts.json").write_text(json.dumps({"alerts": alerts}), encoding="utf-8")
            if isinstance(result, dict):
                self.schedule_agent_update(result.get("agent_update"))
            now = time.monotonic()
            if not self._last_heartbeat_ok_log or now - self._last_heartbeat_ok_log >= 900:
                event(self.logger, "AGENT_HEARTBEAT_OK")
                self._last_heartbeat_ok_log = now
        except Exception as exc:
            event(self.logger, "AGENT_HEARTBEAT_FAILED", exception_type=type(exc).__name__, error=str(exc))
            if strict:
                raise
        if not perform_actions:
            return
        # A transient desktop-notification, update, or heartbeat error must
        # never prevent a previously approved remediation action from running.
        try:
            self._service_action_worker()
        except Exception as exc:
            event(self.logger, "ENDPOINT_ACTION_EXECUTION_FAILED", exception_type=type(exc).__name__, error=str(exc))

    def _service_action_worker(self) -> None:
        with self._action_lock:
            worker = self._action_worker
            action = self._action_current
            started_at = self._action_started_at
            timeout_reported = self._action_timeout_reported
        if worker is not None:
            if worker.is_alive():
                if action and not timeout_reported and time.monotonic() - started_at >= 90:
                    action_id = int(action["id"])
                    action_type = str(action.get("action_type") or "")
                    event(self.logger, "ENDPOINT_ACTION_TIMEOUT", action_id=action_id, action_type=action_type)
                    try:
                        self.transport.action_result(
                            self.config.credential, action_id, False, "Action timed out on the endpoint")
                    except Exception as exc:
                        event(self.logger, "ENDPOINT_ACTION_RESULT_FAILED", action_id=action_id,
                              exception_type=type(exc).__name__, error=str(exc),
                              summary="Action timed out on the endpoint")
                    with self._action_lock:
                        self._action_timeout_reported = True
                return
            with self._action_lock:
                self._action_worker = None
                self._action_current = None
                self._action_timeout_reported = False

        result = self.transport.next_action(self.config.credential)
        action = result.get("action") if isinstance(result, dict) else None
        if not action:
            return
        event(self.logger, "ENDPOINT_ACTION_RECEIVED", action_id=int(action["id"]),
              action_type=str(action.get("action_type") or ""), image=str(action.get("target") or ""))
        worker = threading.Thread(target=self.perform_approved_action, args=(action,),
                                  name="northstar-agent-action-worker", daemon=True)
        with self._action_lock:
            self._action_worker = worker
            self._action_current = action
            self._action_started_at = time.monotonic()
            self._action_timeout_reported = False
        worker.start()

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
        target_text = ".".join(map(str, target_version))
        if previous.get("version") == target_text and previous.get("status") in {"scheduled", "failed"}:
            try:
                attempted = datetime.fromisoformat(str(previous.get("attempted_at") or "").replace("Z", "+00:00"))
                if attempted.tzinfo is None:
                    attempted = attempted.replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc) - attempted < timedelta(hours=24):
                    return
            except (TypeError, ValueError):
                pass
        target = updates_dir / f"NorthstarEndpointAgent-Setup-{'.'.join(map(str, target_version))}.exe"
        try:
            if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest().lower() != digest:
                target.unlink(missing_ok=True)
                self.transport.download(download_path, self.config.credential, target)
            if hashlib.sha256(target.read_bytes()).hexdigest().lower() != digest:
                target.unlink(missing_ok=True)
                raise RuntimeError("downloaded agent update failed checksum validation")
            attempted_at = datetime.now(timezone.utc).isoformat()
            state_path.write_text(json.dumps({"version": target_text, "sha256": digest,
                                               "status": "scheduled", "attempted_at": attempted_at}), encoding="utf-8")
            # Run a separate command process.  Setup stops this scheduled agent
            # before replacing its files, so it must not depend on this process
            # remaining alive after the installer starts.
            command = f'ping 127.0.0.1 -n 6 > nul & start "" /wait "{target}" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /AUTOUPDATE'
            subprocess.Popen(["cmd.exe", "/c", command], close_fds=True,
                             creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) |
                                           getattr(subprocess, "DETACHED_PROCESS", 0))
            event(self.logger, "AGENT_UPDATE_SCHEDULED", version=target_text)
        except Exception as exc:
            state_path.write_text(json.dumps({"version": target_text, "sha256": digest, "status": "failed",
                                               "attempted_at": datetime.now(timezone.utc).isoformat(),
                                               "error": str(exc)[:300]}), encoding="utf-8")
            event(self.logger, "AGENT_UPDATE_FAILED", exception_type=type(exc).__name__)

    def self_repair(self) -> None:
        """Run installation repair independently from inventory and actions."""
        state_path = self.data_dir / "self-repair-state.json"
        summary = {"status": "Skipped", "changed": [], "checked_at": datetime.now(timezone.utc).isoformat()}
        try:
            install_root = Path(sys.executable).resolve().parent
            script = install_root / "repair-agent-install.ps1"
            if os.name != "nt" or not script.is_file():
                summary["status"] = "Unavailable"
            else:
                completed = subprocess.run([
                    os.path.join(os.environ.get("SystemRoot", r"C:\\Windows"),
                                 "System32", "WindowsPowerShell", "v1.0", "powershell.exe"),
                    "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script),
                    "-InstallRoot", str(install_root), "-DataRoot", str(self.data_dir),
                    "-ServerUrl", self.config.server_url, "-CurrentExecutable", str(Path(sys.executable).resolve()),
                ], capture_output=True, text=True, timeout=180,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                output = (completed.stdout or completed.stderr or "").strip()
                changes = [line for line in output.splitlines() if line.strip()][-12:]
                summary.update({"status": ("Repaired" if changes else "Healthy") if completed.returncode == 0 else "Failed",
                                "changed": changes,
                                "exit_code": completed.returncode})
        except Exception as exc:
            summary.update({"status": "Failed", "error": f"{type(exc).__name__}: {exc}"[:400]})
        try:
            state_path.write_text(json.dumps(summary), encoding="utf-8")
        except OSError:
            pass
        event(self.logger, "AGENT_SELF_REPAIR", **summary)

    @staticmethod
    def _run(command: list[str], timeout: int = 30) -> tuple[bool, str]:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                   shell=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
            detail = (stdout or stderr or "").strip()
            return False, (detail or f"Command timed out after {timeout} seconds")[-900:]
        output = (stdout or stderr or "").strip()
        return process.returncode == 0, output[-900:]

    @staticmethod
    def _windows_sessions() -> list[dict]:
        """Enumerate active interactive Windows sessions and their owners."""
        if os.name != "nt":
            return []

        class WTS_SESSION_INFO(ctypes.Structure):
            _fields_ = [
                ("session_id", wintypes.DWORD),
                ("station_name", wintypes.LPWSTR),
                ("state", ctypes.c_int),
            ]

        wts = ctypes.WinDLL("Wtsapi32.dll")
        sessions_pointer = ctypes.POINTER(WTS_SESSION_INFO)()
        count = wintypes.DWORD()
        wts.WTSEnumerateSessionsW.argtypes = [
            wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD,
            ctypes.POINTER(ctypes.POINTER(WTS_SESSION_INFO)), ctypes.POINTER(wintypes.DWORD),
        ]
        wts.WTSEnumerateSessionsW.restype = wintypes.BOOL
        wts.WTSQuerySessionInformationW.argtypes = [
            wintypes.HANDLE, wintypes.DWORD, ctypes.c_int,
            ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.DWORD),
        ]
        wts.WTSQuerySessionInformationW.restype = wintypes.BOOL
        wts.WTSFreeMemory.argtypes = [ctypes.c_void_p]

        def session_text(session_id: int, information_class: int) -> str:
            buffer = ctypes.c_void_p()
            size = wintypes.DWORD()
            if not wts.WTSQuerySessionInformationW(
                    wintypes.HANDLE(0), session_id, information_class,
                    ctypes.byref(buffer), ctypes.byref(size)):
                return ""
            try:
                return ctypes.wstring_at(buffer.value).strip() if buffer.value else ""
            finally:
                if buffer.value:
                    wts.WTSFreeMemory(buffer)

        if not wts.WTSEnumerateSessionsW(
                wintypes.HANDLE(0), 0, 1, ctypes.byref(sessions_pointer), ctypes.byref(count)):
            return []
        try:
            sessions = []
            for index in range(count.value):
                item = sessions_pointer[index]
                if item.state != 0:  # WTSActive
                    continue
                username = session_text(item.session_id, 5)  # WTSUserName
                domain = session_text(item.session_id, 7)  # WTSDomainName
                if username:
                    sessions.append({
                        "session_id": int(item.session_id),
                        "username": username,
                        "domain": domain,
                        "console": str(item.station_name or "").casefold() == "console",
                    })
            return sessions
        finally:
            wts.WTSFreeMemory(sessions_pointer)

    @staticmethod
    def _identity_names(value: object) -> set[str]:
        candidate = str(value or "").strip().casefold()
        if not candidate:
            return set()
        names = {candidate}
        if "\\" in candidate:
            names.add(candidate.rsplit("\\", 1)[-1])
        if "@" in candidate:
            names.add(candidate.split("@", 1)[0])
        return names

    @classmethod
    def _session_id_for_requester(cls, action: dict) -> int | None:
        requested_names = set()
        requested_names.update(cls._identity_names(action.get("requester_username")))
        requested_names.update(cls._identity_names(action.get("requester_upn")))
        sessions = cls._windows_sessions()
        for session in sessions:
            session_names = cls._identity_names(session.get("username"))
            domain = str(session.get("domain") or "").strip()
            if domain and session.get("username"):
                session_names.update(cls._identity_names(f"{domain}\\{session['username']}"))
            if requested_names and requested_names.intersection(session_names):
                return int(session["session_id"])
        # Older servers may not send requester identity, and directory naming
        # can occasionally differ from the WTS username. A single active user
        # is unambiguous; with two or more users, never guess which session owns
        # the request or terminate another person's process.
        return int(sessions[0]["session_id"]) if len(sessions) == 1 else None

    def inventory_timed_out(self) -> None:
        event(self.logger, "DEVICE_INVENTORY_TIMEOUT", timeout_seconds=900)

    def perform_approved_action(self, action: dict | None = None) -> None:
        if action is None:
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
                session_id = self._session_id_for_requester(action)
                match_method = "requester_identity" if (action.get("requester_username") or action.get("requester_upn")) else "single_active_session"
                event(self.logger, "ENDPOINT_ACTION_SESSION_SELECTED", action_id=action_id,
                      session_id=session_id, match_method=match_method if session_id is not None else "none")
                if session_id is None:
                    summary = "The requester is not signed in on this computer."
                else:
                    taskkill = os.path.join(os.environ.get("SystemRoot", r"C:\\Windows"), "System32", "taskkill.exe")
                    if not os.path.isfile(taskkill):
                        taskkill = "taskkill.exe"
                    succeeded, detail = self._run([
                        taskkill, "/F", "/T", "/FI", f"SESSION eq {session_id}",
                        "/FI", f"IMAGENAME eq {image_name}",
                    ], 20)
                    no_matching_process = "no tasks running" in detail.casefold()
                    if no_matching_process:
                        succeeded = False
                    if succeeded:
                        summary = detail or f"Closed {image_name}."
                    elif no_matching_process:
                        summary = f"{image_name} is not running for the signed-in user"
                    else:
                        summary = detail or f"Could not close {image_name}."
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
        with self._action_lock if hasattr(self, "_action_lock") else threading.Lock():
            timed_out = bool(getattr(self, "_action_timeout_reported", False) and
                             getattr(self, "_action_current", {}).get("id") == action_id)
        if timed_out:
            return
        try:
            self.transport.action_result(self.config.credential, action_id, succeeded, summary)
            event(self.logger, "ENDPOINT_ACTION_COMPLETED", action_id=action_id,
                  action_type=action_type, succeeded=succeeded, summary=summary)
        except Exception as exc:
            event(self.logger, "ENDPOINT_ACTION_RESULT_FAILED", action_id=action_id,
                  exception_type=type(exc).__name__, error=str(exc), summary=summary)

    def close(self) -> None:
        self.database.close()


def watchdog_restart_reason(scheduler: Scheduler, maximum_heartbeat_age: int = 300) -> str | None:
    if not scheduler.action_thread.is_alive():
        return "action thread stopped"
    if time.monotonic() - scheduler.last_heartbeat_attempt > maximum_heartbeat_age:
        return "heartbeat attempt stale"
    return None


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
    parser.add_argument("--heartbeat-once", action="store_true")
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
    instance = None if (args.once or args.heartbeat_once) else SingleInstance(args.data_dir / "agent.lock")
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
        if args.heartbeat_once:
            agent.heartbeat(strict=True, perform_actions=False)
            return 0
        event(agent.logger, "AGENT_STARTED", version=__version__)
        scheduler = Scheduler(agent.collect_and_sync, agent.heartbeat,
                              config.full_interval_seconds, config.heartbeat_interval_seconds,
                              refresh_requested=agent.consume_tray_refresh_request,
                              full_timeout=900, full_timeout_action=agent.inventory_timed_out,
                              maintenance_action=agent.self_repair, maintenance_interval=21600,
                              action_error=lambda exc: event(agent.logger, "AGENT_ACTION_LOOP_ERROR",
                                                             exception_type=type(exc).__name__, error=str(exc)))
        scheduler.start()
        stop = threading.Event()
        stop_reason = {"value": "shutdown requested"}
        def request_stop(signum, _frame):
            stop_reason["value"] = f"signal {signum}"
            stop.set()
        signal.signal(signal.SIGINT, request_stop)
        signal.signal(signal.SIGTERM, request_stop)
        exit_code = 0
        while not stop.wait(5):
            reason = watchdog_restart_reason(scheduler)
            if reason:
                event(agent.logger, "AGENT_WATCHDOG_RESTART", reason=reason)
                stop_reason["value"] = reason
                exit_code = 3
                break
        event(agent.logger, "AGENT_STOPPING", reason=stop_reason["value"])
        scheduler.stop()
        event(agent.logger, "AGENT_STOPPED", exit_code=exit_code)
        return exit_code
    finally:
        agent.close()
        if instance:
            instance.release()


if __name__ == "__main__":
    raise SystemExit(main())

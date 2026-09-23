"""Per-user Windows notification-area companion for Northstar Desk.

The inventory process runs as LocalSystem and deliberately has no desktop UI.
This small companion runs in each interactive user session and only opens safe
web destinations; it never reads or receives the endpoint credential.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import sys
import time
from ctypes import wintypes
from datetime import datetime, timezone
from pathlib import Path


def help_desk_urls(server_url: str) -> tuple[str, str, str, str]:
    base = server_url.strip().rstrip("/")
    if not base.lower().startswith(("https://", "http://localhost", "http://127.0.0.1")):
        raise ValueError("The Help Desk URL must use HTTPS (HTTP is allowed only for local testing).")
    return f"{base}/#home", f"{base}/#catalog", f"{base}/#tickets", f"{base}/#notifications"


def run_tray(server_url: str) -> int:
    if os.name != "nt":
        raise RuntimeError("The Northstar tray companion requires Windows.")

    diagnostic_target = os.environ.get("NORTHSTAR_TRAY_DIAGNOSTIC", "").strip()

    def trace_startup(phase: str) -> None:
        """Write opt-in startup evidence without affecting the normal tray path."""
        if not diagnostic_target:
            return
        try:
            # Keep every diagnostic checkpoint.  The old single-record file
            # concealed the exact Windows call at which startup stopped.
            with Path(diagnostic_target).open("a", encoding="utf-8") as target:
                target.write(
                    json.dumps(
                        {
                            "phase": phase,
                            "pid": os.getpid(),
                            "at": datetime.now(timezone.utc).isoformat(),
                            "executable": str(Path(sys.executable).resolve()),
                        }
                    )
                    + "\n"
                )
        except OSError:
            pass

    trace_startup("entered")
    home_url, ticket_url, open_tickets_url, notifications_url = help_desk_urls(server_url)
    tray_data = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "NorthstarEndpointAgent"
    tray_data.mkdir(parents=True, exist_ok=True)
    ready_path = tray_data / "tray.ready.json"
    log_path = tray_data / "tray.log"
    ready_path.unlink(missing_ok=True)
    trace_startup("local_data_ready")

    def tray_log(message: str) -> None:
        # Diagnostics must never terminate the tray companion.  A redirected
        # profile or a temporarily unavailable local profile can make this
        # optional log unwritable.
        try:
            with log_path.open("a", encoding="utf-8") as target:
                target.write(f"{datetime.now(timezone.utc).isoformat()} {message}\n")
        except OSError:
            pass

    def diagnostic_event(event: str, **fields: object) -> None:
        """Append safe, structured delivery diagnostics without ticket content."""
        record = {"event": event, "pid": os.getpid(), "at": datetime.now(timezone.utc).isoformat()}
        for key, value in fields.items():
            if isinstance(value, (str, int, float, bool)) or value is None:
                record[key] = value
        try:
            with log_path.open("a", encoding="utf-8") as target:
                target.write(json.dumps(record, separators=(",", ":")) + "\n")
        except OSError:
            pass
        # When explicitly enabled, mirror the same structured record to the
        # startup diagnostic file so support can correlate server and tray logs.
        if diagnostic_target:
            try:
                with Path(diagnostic_target).open("a", encoding="utf-8") as target:
                    target.write(json.dumps(record, separators=(",", ":")) + "\n")
            except OSError:
                pass

    user32, shell32, kernel32 = ctypes.windll.user32, ctypes.windll.shell32, ctypes.windll.kernel32
    trace_startup("win32_bound")
    # Declare both parameter and return types. Without argtypes ctypes treats
    # native handles as 32-bit integers; the 64-bit module handle is then
    # truncated while CreateWindowExW is called and the tray exits before its
    # icon can be registered.
    kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.GetLastError.argtypes = []
    kernel32.GetLastError.restype = wintypes.DWORD
    kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    kernel32.GetModuleHandleW.restype = wintypes.HINSTANCE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    user32.CreateWindowExW.argtypes = [
        wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID,
    ]
    user32.CreateWindowExW.restype = wintypes.HWND
    user32.SystemParametersInfoW.argtypes = [wintypes.UINT, wintypes.UINT, wintypes.LPVOID, wintypes.UINT]
    user32.SystemParametersInfoW.restype = wintypes.BOOL
    user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                    ctypes.c_int, ctypes.c_int, wintypes.UINT]
    user32.SetWindowPos.restype = wintypes.BOOL
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.ShowWindow.restype = wintypes.BOOL
    user32.UpdateWindow.argtypes = [wintypes.HWND]
    user32.UpdateWindow.restype = wintypes.BOOL
    user32.SetTimer.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.LPVOID]
    user32.SetTimer.restype = ctypes.c_size_t
    user32.KillTimer.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.KillTimer.restype = wintypes.BOOL
    user32.DestroyWindow.argtypes = [wintypes.HWND]
    user32.DestroyWindow.restype = wintypes.BOOL
    user32.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT]
    user32.PeekMessageW.restype = wintypes.BOOL
    user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
    user32.TranslateMessage.restype = wintypes.BOOL
    user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
    user32.DispatchMessageW.restype = wintypes.LPARAM
    user32.CreatePopupMenu.argtypes = []
    user32.CreatePopupMenu.restype = wintypes.HMENU
    user32.LoadIconW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR]
    user32.LoadIconW.restype = wintypes.HICON
    user32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT, ctypes.c_int, ctypes.c_int, wintypes.UINT]
    user32.LoadImageW.restype = wintypes.HANDLE
    shell32.ExtractIconW.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.UINT]
    shell32.ExtractIconW.restype = wintypes.HICON
    user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.DefWindowProcW.restype = wintypes.LPARAM
    WM_DESTROY, WM_COMMAND, WM_TIMER, WM_USER = 0x0002, 0x0111, 0x0113, 0x0400
    PM_REMOVE = 0x0001
    WM_LBUTTONUP, WM_RBUTTONUP, WM_CONTEXTMENU = 0x0202, 0x0205, 0x007B
    NIM_ADD, NIM_MODIFY, NIM_DELETE, NIM_SETVERSION = 0x00000000, 0x00000001, 0x00000002, 0x00000004
    NIF_MESSAGE, NIF_ICON, NIF_TIP, NIF_INFO, NOTIFYICON_VERSION_4 = 0x1, 0x2, 0x4, 0x10, 4
    NIIF_NONE, NIIF_INFO, NIIF_WARNING, NIIF_ERROR = 0x0, 0x1, 0x2, 0x3
    TPM_RIGHTBUTTON, TPM_RETURNCMD = 0x0002, 0x0100
    MF_STRING, MF_SEPARATOR = 0x0000, 0x0800
    WS_POPUP, WS_CHILD, WS_VISIBLE, WS_BORDER = 0x80000000, 0x40000000, 0x10000000, 0x00800000
    WS_EX_TOPMOST, WS_EX_TOOLWINDOW, WS_EX_NOACTIVATE = 0x00000008, 0x00000080, 0x08000000
    SPI_GETWORKAREA, SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE, SWP_SHOWWINDOW, SW_SHOWNOACTIVATE = 48, 0x0001, 0x0002, 0x0010, 0x0040, 4
    HWND_TOPMOST = wintypes.HWND(-1)
    ID_OPEN, ID_TICKET, ID_OPEN_TICKETS, ID_NOTIFICATIONS, ID_REFRESH, ID_TEST_NOTIFICATION, ID_EXIT = 1001, 1002, 1003, 1004, 1005, 1006, 1007
    callback_message = WM_USER + 20

    class GUID(ctypes.Structure):
        _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD),
                    ("Data4", ctypes.c_ubyte * 8)]

    class NOTIFYICONDATAW(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND), ("uID", wintypes.UINT),
                    ("uFlags", wintypes.UINT), ("uCallbackMessage", wintypes.UINT), ("hIcon", wintypes.HICON),
                    ("szTip", wintypes.WCHAR * 128), ("dwState", wintypes.DWORD),
                    ("dwStateMask", wintypes.DWORD), ("szInfo", wintypes.WCHAR * 256),
                    ("uTimeoutOrVersion", wintypes.UINT), ("szInfoTitle", wintypes.WCHAR * 64),
                    ("dwInfoFlags", wintypes.DWORD), ("guidItem", GUID), ("hBalloonIcon", wintypes.HICON)]

    # Pass the real structure pointer.  On 64-bit Windows an untyped LPVOID
    # can be marshalled inconsistently by a frozen executable.
    shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
    shell32.Shell_NotifyIconW.restype = wintypes.BOOL

    WNDPROC = ctypes.WINFUNCTYPE(wintypes.LPARAM, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

    class WNDCLASSW(ctypes.Structure):
        _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                    ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
                    ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
                    ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR)]

    # ctypes otherwise assumes an integer argument for this pointer parameter
    # on some frozen Python builds, which can prevent the tray window from
    # registering during startup.
    user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
    user32.RegisterClassW.restype = wintypes.ATOM

    class RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                    ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

    class_name = "NorthstarEndpointTrayWindow"
    # A notification must own its own window procedure and timer.  A top-level
    # STATIC control can be created successfully but remain invisible on some
    # Windows 11 shells, which is exactly the failure the tray companion was
    # showing.  The dedicated class below is intentionally independent of the
    # tray window so closing a toast cannot terminate the companion.
    toast_class_name = "NorthstarEndpointToastWindow"
    mutex_name = "Local\\NorthstarEndpointTray"
    if diagnostic_target:
        mutex_name = f"{mutex_name}-diagnostic-{os.getpid()}"
    mutex = kernel32.CreateMutexW(None, False, mutex_name)
    # Win32's last-error value belongs to this thread and must be captured
    # immediately. Any logging or file operation between these two calls can
    # overwrite it, incorrectly making a new tray process think one exists.
    mutex_already_exists = kernel32.GetLastError() == 183  # ERROR_ALREADY_EXISTS
    trace_startup("mutex_checked")
    if mutex_already_exists:
        tray_log("Tray companion already running in this user session.")
        kernel32.CloseHandle(mutex)
        return 0

    trace_startup("pre_notify_struct")
    notify = NOTIFYICONDATAW()
    trace_startup("post_notify_struct")
    notify.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
    notify.uID = 1
    trace_startup("notify_fields_ready")
    alerts_path = Path(os.environ.get("PROGRAMDATA") or r"C:\ProgramData") / "NorthstarEndpointAgent" / "tray" / "alerts.json"
    seen_alerts_path = tray_data / "seen-alerts.json"
    last_alert_ticket_id: int | None = None
    toast_hwnd = 0
    trace_startup("notification_state_ready")

    def seen_alert_ids() -> set[str]:
        try:
            values = json.loads(seen_alerts_path.read_text(encoding="utf-8"))
            return {str(item) for item in values if item}
        except (OSError, ValueError, TypeError):
            return set()

    def mark_alert_seen(alert_id: str) -> None:
        values = seen_alert_ids()
        values.add(alert_id)
        # Bound this per-user history: old notices never need to remain local.
        seen_alerts_path.write_text(json.dumps(sorted(values)[-250:]), encoding="utf-8")

    def open_url(url: str) -> None:
        shell32.ShellExecuteW(None, "open", url, None, None, 1)

    def request_refresh() -> None:
        try:
            refresh_path = alerts_path.parent / "refresh.request"
            refresh_path.parent.mkdir(parents=True, exist_ok=True)
            refresh_path.write_text(json.dumps({"requested_at": datetime.now(timezone.utc).isoformat()}), encoding="utf-8")
            tray_log("User requested an agent refresh.")
            present_notification("Help Desk", "Refreshing messages and support requests.", "information")
        except OSError as exc:
            tray_log(f"Could not request agent refresh: {exc}")

    trace_startup("notification_helpers_ready")

    def dismiss_desktop_toast() -> None:
        nonlocal toast_hwnd
        if toast_hwnd:
            diagnostic_event("toast.dismissed")
            user32.KillTimer(toast_hwnd, 2)
            user32.DestroyWindow(toast_hwnd)
            toast_hwnd = 0

    def show_desktop_toast(title: str, body: str, severity: str) -> bool:
        """Show a compact, self-closing desktop notice at the bottom right."""
        nonlocal toast_hwnd
        diagnostic_event("toast.display_started", severity=severity or "information")
        try:
            dismiss_desktop_toast()
            work_area = RECT()
            if not user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(work_area), 0):
                diagnostic_event("toast.display_failed", phase="work_area", win32_error=int(kernel32.GetLastError()))
                tray_log(f"Desktop toast work-area lookup failed with Win32 error {kernel32.GetLastError()}.")
                return False
            width, height, margin = 410, 112, 18
            left = max(work_area.left + margin, work_area.right - width - margin)
            top = max(work_area.top + margin, work_area.bottom - height - margin)
            toast_hwnd = user32.CreateWindowExW(
                WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE,
                toast_class_name, "Help Desk", WS_POPUP | WS_VISIBLE | WS_BORDER,
                left, top, width, height, None, None, instance, None,
            )
            if not toast_hwnd:
                diagnostic_event("toast.display_failed", phase="create_window", win32_error=int(kernel32.GetLastError()))
                tray_log(f"Desktop toast creation failed with Win32 error {kernel32.GetLastError()}.")
                return False
            badge = {"critical": "CRITICAL", "error": "CRITICAL", "warning": "WARNING"}.get(severity, "INFO")
            user32.CreateWindowExW(0, "STATIC", f"HELP DESK  |  {badge}", WS_CHILD | WS_VISIBLE,
                                   16, 12, width - 32, 20, toast_hwnd, None, instance, None)
            user32.CreateWindowExW(0, "STATIC", str(title)[:120], WS_CHILD | WS_VISIBLE,
                                   16, 36, width - 32, 24, toast_hwnd, None, instance, None)
            user32.CreateWindowExW(0, "STATIC", str(body)[:220], WS_CHILD | WS_VISIBLE,
                                   16, 64, width - 32, 30, toast_hwnd, None, instance, None)
            # Reassert the placement after creating child text controls.  This is
            # necessary for a no-activation window on Windows 10/11, otherwise a
            # popup can be created behind the active window and appear invisible.
            if not user32.SetWindowPos(
                toast_hwnd,
                HWND_TOPMOST,
                left,
                top,
                width,
                height,
                SWP_SHOWWINDOW | SWP_NOACTIVATE,
            ):
                diagnostic_event("toast.display_failed", phase="position", win32_error=int(kernel32.GetLastError()))
                tray_log(f"Desktop toast placement failed with Win32 error {kernel32.GetLastError()}.")
                dismiss_desktop_toast()
                return False
            # Force the no-activation window to paint immediately.  Some
            # Windows 11 shells otherwise defer painting a WS_EX_NOACTIVATE
            # popup until the user changes focus, which makes a notification
            # look as though it never appeared.
            user32.ShowWindow(toast_hwnd, SW_SHOWNOACTIVATE)
            if not user32.UpdateWindow(toast_hwnd):
                diagnostic_event("toast.display_failed", phase="paint", win32_error=int(kernel32.GetLastError()))
                tray_log(f"Desktop toast paint failed with Win32 error {kernel32.GetLastError()}.")
                dismiss_desktop_toast()
                return False
            if not user32.SetTimer(toast_hwnd, 2, 7000, None):
                diagnostic_event("toast.display_failed", phase="timer", win32_error=int(kernel32.GetLastError()))
                tray_log(f"Desktop toast timer failed with Win32 error {kernel32.GetLastError()}.")
                dismiss_desktop_toast()
                return False
            tray_log(f"Desktop toast displayed: severity={severity or 'information'} title={str(title)[:80]!r}.")
            diagnostic_event("toast.displayed", severity=severity or "information")
            return True
        except Exception as exc:
            diagnostic_event("toast.display_failed", phase="exception", exception_type=type(exc).__name__)
            trace_startup(f"desktop_toast_exception_{type(exc).__name__}_{str(exc)[:180]}")
            tray_log(f"Desktop toast failed: {exc}")
            dismiss_desktop_toast()
            return False

    def show_notification_area_alert(title: str, body: str, severity: str) -> bool:
        """Use the Windows notification area as a reliable fallback for the desktop toast."""
        try:
            severity_flag = {
                "critical": NIIF_ERROR,
                "error": NIIF_ERROR,
                "warning": NIIF_WARNING,
                "warn": NIIF_WARNING,
            }.get((severity or "").lower(), NIIF_INFO)
            balloon = NOTIFYICONDATAW()
            balloon.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
            balloon.hWnd = notify.hWnd
            balloon.uID = notify.uID
            balloon.uFlags = NIF_INFO
            balloon.szInfoTitle = str(title or "Help Desk")[:63]
            balloon.szInfo = str(body or "You have a Help Desk update.")[:255]
            balloon.uTimeoutOrVersion = 7000
            balloon.dwInfoFlags = severity_flag
            displayed = bool(shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(balloon)))
            if displayed:
                diagnostic_event("notification_area.displayed", severity=severity or "information")
                tray_log(f"Notification-area alert displayed: severity={severity or 'information'} title={str(title)[:80]!r}.")
            else:
                diagnostic_event("notification_area.failed", win32_error=int(kernel32.GetLastError()))
                tray_log(f"Notification-area alert failed with Win32 error {kernel32.GetLastError()}.")
            return displayed
        except Exception as exc:
            diagnostic_event("notification_area.failed", exception_type=type(exc).__name__)
            tray_log(f"Notification-area alert failed: {exc}")
            return False

    def present_notification(title: str, body: str, severity: str) -> bool:
        """Present activity through both supported Windows notification paths."""
        diagnostic_event("notification.dispatch", severity=severity or "information")
        desktop_presented = show_desktop_toast(title, body, severity)
        area_presented = show_notification_area_alert(title, body, severity)
        diagnostic_event("notification.result", desktop=desktop_presented, notification_area=area_presented,
                         presented=desktop_presented or area_presented)
        return desktop_presented or area_presented

    trace_startup("toast_helpers_ready")

    def show_menu(hwnd: int) -> None:
        menu = user32.CreatePopupMenu()
        user32.AppendMenuW(menu, MF_STRING, ID_OPEN, "Open Help Desk")
        user32.AppendMenuW(menu, MF_STRING, ID_TICKET, "Create a Ticket")
        user32.AppendMenuW(menu, MF_STRING, ID_OPEN_TICKETS, "My Open Tickets")
        user32.AppendMenuW(menu, MF_STRING, ID_NOTIFICATIONS, "Messages and Notifications")
        user32.AppendMenuW(menu, MF_STRING, ID_REFRESH, "Refresh Help Desk agent")
        user32.AppendMenuW(menu, MF_STRING, ID_TEST_NOTIFICATION, "Test notification")
        user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(menu, MF_STRING, ID_EXIT, "Exit tray companion")
        point = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(point))
        user32.SetForegroundWindow(hwnd)
        command = user32.TrackPopupMenu(menu, TPM_RIGHTBUTTON | TPM_RETURNCMD,
                                        point.x, point.y, 0, hwnd, None)
        user32.DestroyMenu(menu)
        if command == ID_OPEN:
            open_url(home_url)
        elif command == ID_TICKET:
            open_url(ticket_url)
        elif command == ID_OPEN_TICKETS:
            open_url(open_tickets_url)
        elif command == ID_NOTIFICATIONS:
            open_url(notifications_url)
        elif command == ID_REFRESH:
            request_refresh()
            poll_alerts()
        elif command == ID_TEST_NOTIFICATION:
            present_notification(
                "Help Desk notification test",
                "This is a test notification. It closes automatically in a few seconds.",
                "information",
            )
        elif command == ID_EXIT:
            user32.DestroyWindow(hwnd)

    def poll_alerts() -> None:
        nonlocal last_alert_ticket_id
        try:
            alerts = json.loads(alerts_path.read_text(encoding="utf-8")).get("alerts", []) if alerts_path.is_file() else []
            seen = seen_alert_ids()
            newest = next((item for item in alerts if str(item.get("id") or "") not in seen), None)
            if not newest:
                return
            alert_id = str(newest.get("id") or "")
            ticket_id = newest.get("ticket_id")
            diagnostic_event("notification.received", alert_id=alert_id or None,
                             ticket_id=int(ticket_id) if ticket_id is not None else None,
                             severity=str(newest.get("severity") or "information").lower())
            last_alert_ticket_id = int(ticket_id) if ticket_id is not None else None
            severity = str(newest.get("severity") or "information").lower()
            # Windows can silently suppress legacy notification-area balloons.
            # Use the agent's own small desktop toast so Help Desk activity is
            # visible regardless of the user's Action Center policy.
            presented = present_notification(
                str(newest.get("title") or "Help Desk"),
                str(newest.get("body") or "You have a Help Desk update."),
                severity,
            )
            # Do not consume a notification unless Windows actually accepted the
            # popup.  That makes a failed notification retry on the next poll
            # instead of disappearing silently.
            if presented and alert_id:
                mark_alert_seen(alert_id)
                diagnostic_event("notification.seen", alert_id=alert_id)
            elif not presented:
                diagnostic_event("notification.retry", alert_id=alert_id or None)
                tray_log(f"Alert {alert_id or '<without-id>'} will retry because its desktop toast was not presented.")
        except (OSError, ValueError, TypeError) as exc:
            diagnostic_event("notification.poll_failed", exception_type=type(exc).__name__)
            return

    trace_startup("polling_helpers_ready")

    @WNDPROC
    def window_proc(hwnd, message, wparam, lparam):
        if message == callback_message:
            event = int(lparam) & 0xFFFF
            if event in (WM_LBUTTONUP, WM_RBUTTONUP, WM_CONTEXTMENU):
                show_menu(hwnd)
                return 0
            if event == 0x0405:  # NIN_BALLOONUSERCLICK
                open_url(f"{server_url.strip().rstrip('/')}/#ticket/{last_alert_ticket_id}" if last_alert_ticket_id else notifications_url)
                return 0
        if message == WM_COMMAND:
            return 0
        if message == WM_TIMER:
            if int(wparam) == 1:
                poll_alerts()
            return 0
        if message == WM_DESTROY:
            shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(notify))
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, message, wparam, lparam)

    @WNDPROC
    def toast_window_proc(toast_handle, message, wparam, lparam):
        """Keep toast lifetime separate from the hidden tray window."""
        nonlocal toast_hwnd
        if message == WM_TIMER and int(wparam) == 2:
            user32.KillTimer(toast_handle, 2)
            user32.DestroyWindow(toast_handle)
            return 0
        if message == WM_DESTROY:
            if toast_hwnd == toast_handle:
                toast_hwnd = 0
            return 0
        return user32.DefWindowProcW(toast_handle, message, wparam, lparam)

    trace_startup("pre_module_handle")
    instance = kernel32.GetModuleHandleW(None)
    trace_startup("module_handle_ready")
    window_class = WNDCLASSW(0, window_proc, 0, 0, instance, None, None, None, None, class_name)
    trace_startup("pre_window_class_register")
    atom = user32.RegisterClassW(ctypes.byref(window_class))
    trace_startup("window_class_registered")
    if not atom and kernel32.GetLastError() != 1410:  # class already exists is harmless
        tray_log(f"Window class registration failed with Win32 error {kernel32.GetLastError()}.")
        kernel32.CloseHandle(mutex)
        return 1
    # Give the popup its own normal window background.  A system-colour brush
    # is represented by COLOR_WINDOW + 1; this avoids an untyped
    # GetSysColorBrush call in a frozen 64-bit executable (which can truncate
    # the handle and stop the whole tray process during class registration).
    toast_window_class = WNDCLASSW()
    toast_window_class.style = 0
    toast_window_class.lpfnWndProc = toast_window_proc
    toast_window_class.hInstance = instance
    toast_window_class.hbrBackground = wintypes.HBRUSH(6)  # COLOR_WINDOW + 1
    toast_window_class.lpszClassName = toast_class_name
    toast_atom = user32.RegisterClassW(ctypes.byref(toast_window_class))
    if not toast_atom and kernel32.GetLastError() != 1410:  # class already exists is harmless
        # The companion remains available even if a Windows shell blocks the
        # optional popup class.  Fall back to the stable tray class instead of
        # taking the user-facing agent offline.
        tray_log(f"Toast window class registration failed with Win32 error {kernel32.GetLastError()}; using tray-class fallback.")
        toast_class_name = class_name
    hwnd = user32.CreateWindowExW(0, class_name, "Help Desk", 0, 0, 0, 0, 0,
                                  None, None, instance, None)
    trace_startup("window_created")
    if not hwnd:
        tray_log(f"Tray window creation failed with Win32 error {kernel32.GetLastError()}.")
        kernel32.CloseHandle(mutex)
        return 1
    notify.hWnd = hwnd
    notify.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
    notify.uCallbackMessage = callback_message
    # A PyInstaller executable can expose Windows' generic application icon.
    # Prefer the dedicated icon installed beside the tray companion.
    icon_path = Path(sys.executable).with_name("northstar.ico")
    IMAGE_ICON, LR_LOADFROMFILE = 1, 0x0010
    if icon_path.is_file():
        notify.hIcon = user32.LoadImageW(None, str(icon_path), IMAGE_ICON, 32, 32, LR_LOADFROMFILE)
    if not notify.hIcon:
        notify.hIcon = shell32.ExtractIconW(None, ctypes.c_wchar_p(sys.executable), 0)
    if not notify.hIcon:
        notify.hIcon = user32.LoadIconW(None, ctypes.c_wchar_p(32512))  # IDI_APPLICATION fallback
    notify.szTip = "Help Desk - right-click for options"
    # Test mode deliberately exercises the desktop-toast path before talking
    # to Explorer's notification-area API.  This keeps the test independent
    # from whether a tray icon is available in the current Windows session.
    if os.environ.get("NORTHSTAR_TRAY_TEST_NOTIFICATION", "").strip() == "1":
        trace_startup("pre_test_desktop_toast")
        test_desktop_toast = show_desktop_toast(
            "Help Desk notification test",
            "This is a test notification. It closes automatically in a few seconds.",
            "information",
        )
        trace_startup(f"test_desktop_toast_returned_{int(bool(test_desktop_toast))}")
        # This isolated test deliberately does not depend on Explorer's tray
        # API. Pump messages long enough for Windows to render and dismiss the
        # visible toast, then cleanly exit without registering a tray icon.
        deadline = time.monotonic() + 8.0
        message = wintypes.MSG()
        while time.monotonic() < deadline:
            while user32.PeekMessageW(ctypes.byref(message), None, 0, 0, PM_REMOVE):
                user32.TranslateMessage(ctypes.byref(message))
                user32.DispatchMessageW(ctypes.byref(message))
            time.sleep(0.03)
        dismiss_desktop_toast()
        user32.DestroyWindow(hwnd)
        kernel32.CloseHandle(mutex)
        trace_startup("test_desktop_toast_completed")
        return 0 if test_desktop_toast else 1
    trace_startup("pre_tray_icon_add")
    tray_added = shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(notify))
    tray_add_error = kernel32.GetLastError()
    trace_startup(f"tray_icon_add_returned_{int(bool(tray_added))}_err_{tray_add_error}")
    if not tray_added:
        tray_log(f"Windows rejected the tray icon with Win32 error {kernel32.GetLastError()}.")
        user32.DestroyWindow(hwnd)
        kernel32.CloseHandle(mutex)
        return 1
    trace_startup("tray_icon_added")
    notify.uTimeoutOrVersion = NOTIFYICON_VERSION_4
    trace_startup("pre_tray_icon_version")
    tray_version_set = shell32.Shell_NotifyIconW(NIM_SETVERSION, ctypes.byref(notify))
    trace_startup(f"tray_icon_version_returned_{int(bool(tray_version_set))}")
    if not tray_version_set:
        tray_log(f"Tray icon version negotiation failed with Win32 error {kernel32.GetLastError()}.")
        shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(notify))
        user32.DestroyWindow(hwnd)
        kernel32.CloseHandle(mutex)
        return 1
    trace_startup("tray_icon_ready")
    started_at = datetime.now(timezone.utc).isoformat()
    ready_path.write_text(json.dumps({"pid": os.getpid(), "ready_at": started_at}), encoding="utf-8")
    # A runtime marker proves the currently running tray belongs to this exact
    # installed binary. It contains no credential or inventory information.
    (tray_data / "tray-runtime.json").write_text(
        json.dumps(
            {
                "pid": os.getpid(),
                "ready_at": started_at,
                "executable": str(Path(sys.executable).resolve()),
                "tray_menu_test_notification": True,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    trace_startup("runtime_marker_written")
    # The agent service refreshes this small local signal every minute; the
    # tray checks it promptly so an alert feels immediate once received.
    user32.SetTimer(hwnd, 1, 5000, None)
    poll_alerts()
    tray_log(f"Tray icon registered successfully for process {os.getpid()}.")
    message = wintypes.MSG()
    while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
        user32.TranslateMessage(ctypes.byref(message))
        user32.DispatchMessageW(ctypes.byref(message))
    ready_path.unlink(missing_ok=True)
    (tray_data / "tray-runtime.json").unlink(missing_ok=True)
    kernel32.CloseHandle(mutex)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Northstar Endpoint Agent tray companion")
    parser.add_argument("--server")
    parser.add_argument("--build-evidence", help="Write packaged tray capability evidence to this file")
    args = parser.parse_args(argv)
    if args.build_evidence:
        Path(args.build_evidence).write_text(
            json.dumps(
                {
                    "tray_menu_test_notification": True,
                    "release": "agent-toast-menu",
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return 0
    if not args.server:
        parser.error("--server is required")
    return run_tray(args.server)


if __name__ == "__main__":
    raise SystemExit(main())

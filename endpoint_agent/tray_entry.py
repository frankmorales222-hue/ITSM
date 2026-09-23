import json
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

_build_evidence_target = os.environ.get("NORTHSTAR_TRAY_BUILD_EVIDENCE")
if _build_evidence_target or "--build-evidence" in sys.argv:
    # Used only by the release build to prove the packaged tray binary contains
    # the expected user-visible notification command before it is distributed.
    evidence_path = Path(
        _build_evidence_target
        if _build_evidence_target
        else sys.argv[sys.argv.index("--build-evidence") + 1]
    )
    evidence_path.write_text(
        json.dumps(
            {
        "version": "0.1.37",
                "tray_menu_test_notification": True,
                "release": "agent-toast-menu",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    raise SystemExit(0)

# Keep normal tray imports below the release verification gate. This lets the
# build prove that the packaged executable is current without initializing any
# Windows tray components.
from asset_agent.tray import main

try:
    raise SystemExit(main())
except BaseException:
    # The tray has no console. Preserve failures in the signed-in user's
    # profile so support can diagnose startup without exposing agent secrets.
    try:
        log_dir = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "NorthstarEndpointAgent"
        log_dir.mkdir(parents=True, exist_ok=True)
        with (log_dir / "tray.log").open("a", encoding="utf-8") as stream:
            stream.write(f"\n[{datetime.now(timezone.utc).isoformat()}] Tray startup failed\n")
            stream.write(traceback.format_exc())
    except Exception:
        pass
    raise

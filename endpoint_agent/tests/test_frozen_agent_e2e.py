import json
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest


AGENT_EXE = Path(__file__).resolve().parents[1] / "dist" / "NorthstarEndpointAgent.exe"


class _AgentApiHandler(BaseHTTPRequestHandler):
    inventory_status = 200
    requests = []

    def log_message(self, *_args):
        return

    def _body(self):
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length) or b"{}")

    def _reply(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        payload = self._body()
        type(self).requests.append((self.command, self.path, payload, self.headers.get("Authorization")))
        if self.path == "/api/agent/enroll":
            self._reply(201, {"agent_id": "agent-test", "credential": "credential-test"})
        else:
            self._reply(404, {"detail": "not found"})

    def do_PUT(self):
        payload = self._body()
        type(self).requests.append((self.command, self.path, payload, self.headers.get("Authorization")))
        if self.path == "/api/agent/inventory":
            if type(self).inventory_status == 200:
                self._reply(200, {"accepted": True})
            else:
                self._reply(type(self).inventory_status, {"detail": "forced inventory failure"})
        else:
            self._reply(404, {"detail": "not found"})


@pytest.fixture
def agent_api():
    _AgentApiHandler.inventory_status = 200
    _AgentApiHandler.requests = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _AgentApiHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def _run_agent(server, data_dir):
    assert AGENT_EXE.exists(), f"Frozen agent is missing: {AGENT_EXE}"
    return subprocess.run(
        [
            str(AGENT_EXE),
            "--data-dir", str(data_dir),
            "--server", f"http://127.0.0.1:{server.server_port}",
            "--enrollment-token", "one-time-test-token",
            "--once",
        ],
        text=True,
        capture_output=True,
        timeout=180,
        check=False,
    )


def test_frozen_agent_enrolls_and_uploads_first_inventory(agent_api, tmp_path):
    result = _run_agent(agent_api, tmp_path / "success")
    assert result.returncode == 0, result.stdout + result.stderr
    assert (tmp_path / "success" / "config.json").exists()
    paths = [request[1] for request in _AgentApiHandler.requests]
    assert paths == ["/api/agent/enroll", "/api/agent/inventory"]
    inventory = _AgentApiHandler.requests[1]
    assert inventory[3] == "Bearer credential-test"
    assert inventory[2].get("device", {}).get("hostname")


def test_frozen_agent_fails_install_contract_when_first_upload_fails(agent_api, tmp_path):
    _AgentApiHandler.inventory_status = 500
    data_dir = tmp_path / "failure"
    result = _run_agent(agent_api, data_dir)
    assert result.returncode != 0
    log = (data_dir / "agent.log").read_text(encoding="utf-8")
    assert "INVENTORY_SYNC_FAILED" in log
    assert "forced inventory failure" in log

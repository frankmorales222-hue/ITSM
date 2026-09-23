import json
import hashlib
import http.client
import ssl
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit


class InventoryTransport:
    def __init__(self, server_url: str, timeout: int = 30, tls_certificate_sha256: str = ""):
        self.server_url = server_url.rstrip("/")
        self.timeout = timeout
        self.context = ssl.create_default_context()
        self.tls_certificate_sha256 = tls_certificate_sha256.replace(":", "").strip().lower()
        if self.tls_certificate_sha256 and (len(self.tls_certificate_sha256) != 64 or
                                            any(c not in "0123456789abcdef" for c in self.tls_certificate_sha256)):
            raise ValueError("TLS certificate fingerprint must be 64 hexadecimal characters")

    def _pinned_https_request(self, method: str, url: str, body: bytes | None, headers: dict[str, str]) -> dict:
        parsed = urlsplit(url)
        context = ssl._create_unverified_context()
        connection = http.client.HTTPSConnection(parsed.hostname, parsed.port or 443,
                                                  timeout=self.timeout, context=context)
        try:
            connection.connect()
            certificate = connection.sock.getpeercert(binary_form=True) if connection.sock else None
            actual = hashlib.sha256(certificate or b"").hexdigest()
            if not certificate or actual != self.tls_certificate_sha256:
                raise RuntimeError("inventory server TLS certificate does not match the approved fingerprint")
            target = parsed.path or "/"
            if parsed.query:
                target += "?" + parsed.query
            connection.request(method, target, body=body, headers=headers)
            response = connection.getresponse()
            response_body = response.read()
            if response.status >= 400:
                detail = response_body[:2048].decode(errors="replace")
                raise RuntimeError(f"server returned HTTP {response.status}: {detail}")
            return json.loads(response_body.decode())
        except (OSError, ssl.SSLError) as exc:
            raise RuntimeError(f"cannot reach inventory server: {exc}") from exc
        finally:
            connection.close()

    def _request(self, method: str, path: str, payload: dict | None = None, credential: str | None = None) -> dict:
        headers = {"Content-Type": "application/json", "User-Agent": "Northstar-Endpoint-Agent/0.1"}
        if credential:
            headers["Authorization"] = f"Bearer {credential}"
        url = f"{self.server_url}{path}"
        body = json.dumps(payload).encode() if payload is not None else None
        if self.tls_certificate_sha256 and url.lower().startswith("https://"):
            return self._pinned_https_request(method, url, body, headers)
        request = urllib.request.Request(url, data=body,
                                         headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout, context=self.context) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as exc:
            detail = exc.read(2048).decode(errors="replace")
            raise RuntimeError(f"server returned HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"cannot reach inventory server: {exc.reason}") from exc

    def enroll(self, enrollment_token: str, device_id: str, hostname: str, agent_version: str,
               schema_version: int = 1) -> dict:
        return self._request("POST", "/api/agent/enroll", {
            "enrollment_token": enrollment_token, "device_id": device_id, "hostname": hostname,
            "agent_version": agent_version, "schema_version": schema_version,
        })

    def upload(self, credential: str, inventory: dict) -> dict:
        return self._request("PUT", "/api/agent/inventory", inventory, credential)

    def heartbeat(self, credential: str, payload: dict) -> dict:
        return self._request("POST", "/api/agent/heartbeat", payload, credential)

    def next_action(self, credential: str) -> dict:
        return self._request("GET", "/api/agent/actions/next", credential=credential)

    def action_result(self, credential: str, action_id: int, succeeded: bool, summary: str) -> dict:
        return self._request("POST", f"/api/agent/actions/{action_id}/result", {
            "succeeded": succeeded, "summary": summary[:500],
        }, credential)

    def download(self, path: str, credential: str, destination: Path) -> None:
        """Download an authenticated agent update and leave validation to Agent."""
        headers = {"Authorization": f"Bearer {credential}", "User-Agent": "Northstar-Endpoint-Agent/0.1"}
        url = f"{self.server_url}{path}"
        request = urllib.request.Request(url, headers=headers, method="GET")
        try:
            if self.tls_certificate_sha256 and url.lower().startswith("https://"):
                parsed = urlsplit(url)
                context = ssl._create_unverified_context()
                connection = http.client.HTTPSConnection(parsed.hostname, parsed.port or 443,
                                                          timeout=self.timeout, context=context)
                try:
                    connection.connect()
                    certificate = connection.sock.getpeercert(binary_form=True) if connection.sock else None
                    if not certificate or hashlib.sha256(certificate).hexdigest() != self.tls_certificate_sha256:
                        raise RuntimeError("inventory server TLS certificate does not match the approved fingerprint")
                    connection.request("GET", parsed.path or "/", headers=headers)
                    response = connection.getresponse()
                    if response.status >= 400:
                        raise RuntimeError(f"server returned HTTP {response.status}")
                    destination.write_bytes(response.read())
                finally:
                    connection.close()
            else:
                with urllib.request.urlopen(request, timeout=self.timeout, context=self.context) as response:
                    destination.write_bytes(response.read())
        except (OSError, ssl.SSLError, urllib.error.URLError) as exc:
            raise RuntimeError(f"cannot download agent update: {exc}") from exc

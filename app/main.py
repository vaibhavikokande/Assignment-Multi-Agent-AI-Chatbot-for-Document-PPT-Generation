from __future__ import annotations

import cgi
import json
import mimetypes
import posixpath
import secrets
import sys
import tempfile
from http.cookies import SimpleCookie
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .agents import SupervisorAgent, convert_artifact
from .config import get_settings
from .parsers import parse_file
from .repository import ArtifactRepository


settings = get_settings()
repository = ArtifactRepository(settings)
supervisor = SupervisorAgent(repository, web_search_enabled=settings.web_search_enabled)
STATIC_DIR = Path(__file__).parent / "static"
UI_SESSION_TOKEN = secrets.token_urlsafe(32)


class POCHandler(BaseHTTPRequestHandler):
    server_version = "DocumentPPTPOC/1.0"

    def _cors_headers(self) -> dict[str, str]:
        origin = self.headers.get("Origin")
        if origin and origin in settings.allowed_origins:
            return {
                "Access-Control-Allow-Origin": origin,
                "Access-Control-Allow-Credentials": "true",
                "Vary": "Origin",
            }
        return {}

    def _send_json(self, payload: dict, status: int = HTTPStatus.OK) -> None:
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for key, value in self._cors_headers().items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _send_bytes(self, data: bytes, content_type: str, file_name: str | None = None, extra_headers: dict[str, str] | None = None) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        if file_name:
            self.send_header("Content-Disposition", f'attachment; filename="{Path(file_name).name}"')
        for key, value in self._cors_headers().items():
            self.send_header(key, value)
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(data)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length > settings.max_upload_bytes:
            raise ValueError("Request body is too large")
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8"))

    def _error(self, message: str, status: int = HTTPStatus.BAD_REQUEST) -> None:
        self._send_json({"error": message}, status)

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        for key, value in self._cors_headers().items():
            self.send_header(key, value)
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-API-Key")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            if not self._authorized(path):
                return
            if path == "/api/health":
                self._send_json({"status": "ok", "service": "multi-agent-document-ppt-poc", "demo_mode": settings.demo_mode})
                return
            if path == "/api/uploads":
                self._send_json({"uploads": repository.list_uploads()})
                return
            if path == "/api/artifacts":
                self._send_json({"artifacts": repository.list_artifacts()})
                return
            if path.startswith("/api/runs/"):
                run = repository.get_run(path.rsplit("/", 1)[-1])
                if not run:
                    self._error("Run not found", HTTPStatus.NOT_FOUND)
                else:
                    self._send_json(run)
                return
            if path.startswith("/api/artifacts/"):
                parts = path.split("/")
                artifact_id = parts[3] if len(parts) > 3 else ""
                if len(parts) > 4 and parts[4] == "download":
                    query = parse_qs(parsed.query)
                    version = int(query["version"][0]) if query.get("version") else None
                    artifact = repository.get_artifact(artifact_id)
                    if not artifact:
                        self._error("Artifact not found", HTTPStatus.NOT_FOUND)
                        return
                    target = artifact["versions"][-1] if version is None else next((item for item in artifact["versions"] if item["version"] == version), None)
                    if not target:
                        self._error("Artifact version not found", HTTPStatus.NOT_FOUND)
                        return
                    file_path = repository.settings.storage_dir / target["relative_path"]
                    content_type = mimetypes.guess_type(target["file_name"])[0] or "application/octet-stream"
                    self._send_bytes(file_path.read_bytes(), content_type, target["file_name"])
                else:
                    artifact = repository.get_artifact(artifact_id)
                    if not artifact:
                        self._error("Artifact not found", HTTPStatus.NOT_FOUND)
                    else:
                        self._send_json(artifact)
                return
            self._serve_static(path)
        except KeyError as exc:
            message = str(exc.args[0]) if exc.args else "Not found"
            self._error(message, HTTPStatus.NOT_FOUND if message.startswith("Unknown ") else HTTPStatus.BAD_REQUEST)
        except (ValueError, OSError, json.JSONDecodeError) as exc:
            self._error(str(exc), HTTPStatus.BAD_REQUEST)

    def _serve_static(self, path: str) -> None:
        relative = posixpath.normpath(path.lstrip("/"))
        if relative in {"", "."}:
            relative = "index.html"
        candidate = (STATIC_DIR / relative).resolve()
        if STATIC_DIR.resolve() not in candidate.parents and candidate != STATIC_DIR.resolve():
            self._error("Invalid path", HTTPStatus.NOT_FOUND)
            return
        if not candidate.exists() or not candidate.is_file():
            self._error("Not found", HTTPStatus.NOT_FOUND)
            return
        headers = {}
        if relative == "index.html" and settings.api_key:
            headers["Set-Cookie"] = f"poc_session={UI_SESSION_TOKEN}; HttpOnly; SameSite=Strict; Path=/"
        self._send_bytes(candidate.read_bytes(), mimetypes.guess_type(candidate.name)[0] or "application/octet-stream", extra_headers=headers)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            if not self._authorized(parsed.path):
                return
            if parsed.path == "/api/upload":
                self._handle_upload()
                return
            if parsed.path == "/api/chat":
                data = self._read_json()
                message = str(data.get("message", "")).strip()
                if not message:
                    raise ValueError("message is required")
                upload_ids = data.get("upload_ids") or []
                if isinstance(upload_ids, str):
                    upload_ids = [upload_ids]
                run = supervisor.run(message, upload_ids, data.get("artifact_id"), int(data.get("slide_count", 12)))
                self._send_json(run, HTTPStatus.OK if run.get("status") == "completed" else HTTPStatus.INTERNAL_SERVER_ERROR)
                return
            if parsed.path == "/api/convert":
                data = self._read_json()
                result = convert_artifact(repository, str(data["artifact_id"]), str(data["target_format"]), str(data.get("request", "Convert artifact")))
                self._send_json(result)
                return
            self._error("Not found", HTTPStatus.NOT_FOUND)
        except KeyError as exc:
            message = str(exc.args[0]) if exc.args else "Missing field"
            if message.startswith("Unknown "):
                self._error(message, HTTPStatus.NOT_FOUND)
            else:
                self._error(f"Missing field: {exc}")
        except (ValueError, OSError, RuntimeError, json.JSONDecodeError) as exc:
            self._error(str(exc))

    def _handle_upload(self) -> None:
        content_type = self.headers.get("Content-Type", "")
        if not content_type.startswith("multipart/form-data"):
            raise ValueError("Upload must use multipart/form-data")
        length = int(self.headers.get("Content-Length", "0"))
        if length > settings.max_upload_bytes:
            raise ValueError("Upload is too large")
        environ = {
            "REQUEST_METHOD": "POST",
            "CONTENT_TYPE": content_type,
            "CONTENT_LENGTH": str(length),
        }
        form = cgi.FieldStorage(fp=self.rfile, headers=self.headers, environ=environ, keep_blank_values=True)
        item = form["file"] if "file" in form else None
        if item is None or not getattr(item, "filename", None):
            raise ValueError("multipart field 'file' is required")
        data = item.file.read()
        if len(data) > settings.max_upload_bytes:
            raise ValueError("Upload is too large")
        suffix = Path(item.filename).suffix.lower() or ".upload"
        with tempfile.TemporaryDirectory(prefix="upload-stage-") as staging_dir:
            staged_path = Path(staging_dir) / f"staged{suffix}"
            staged_path.write_bytes(data)
            profile = parse_file(staged_path, item.filename, settings.ocr_enabled)
        record = repository.save_upload(item.filename, data)
        self._send_json({"upload": record, "profile": profile.to_dict()})

    def _authorized(self, path: str) -> bool:
        if not settings.api_key or not path.startswith("/api/") or path == "/api/health":
            return True
        if self.headers.get("X-API-Key") == settings.api_key:
            return True
        cookies = SimpleCookie(self.headers.get("Cookie", ""))
        if cookies.get("poc_session") and cookies["poc_session"].value == UI_SESSION_TOKEN:
            return True
        self._send_json({"error": "Authentication required; provide X-API-Key"}, HTTPStatus.UNAUTHORIZED)
        return False

    def log_message(self, format: str, *args: object) -> None:
        sys.stderr.write(f"[poc] {self.address_string()} {format % args}\n")


def serve() -> None:
    server = ThreadingHTTPServer((settings.app_host, settings.app_port), POCHandler)
    print(f"Document/PPT POC running at http://{settings.app_host}:{settings.app_port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    serve()

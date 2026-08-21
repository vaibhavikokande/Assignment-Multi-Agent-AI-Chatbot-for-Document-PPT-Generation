from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from http.client import HTTPConnection
from pathlib import Path

from samples.create_samples import create_sample_docx, create_sample_pptx


ROOT = Path(__file__).parents[1]

# A full supervisor run generates, validates, and re-parses both artifacts. On a
# cold or loaded machine that lands close to 15s, which made these assertions fail
# on timing rather than behaviour. The limits below only need to be generous enough
# to keep the test measuring correctness.
STARTUP_TIMEOUT_SECONDS = 60
REQUEST_TIMEOUT_SECONDS = 120


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _multipart(file_name: str, data: bytes) -> tuple[bytes, str]:
    boundary = "----DocumentPPTComplianceBoundary"
    body = (
        f"--{boundary}\r\n"
        f"Content-Disposition: form-data; name=\"file\"; filename=\"{file_name}\"\r\n"
        "Content-Type: application/octet-stream\r\n\r\n"
    ).encode("utf-8") + data + f"\r\n--{boundary}--\r\n".encode("utf-8")
    return body, f"multipart/form-data; boundary={boundary}"


class APIEndToEndTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp = tempfile.TemporaryDirectory(prefix="document-ppt-api-")
        root = Path(cls.temp.name)
        cls.doc = create_sample_docx(root / "Company_Proposal.docx")
        cls.ppt = create_sample_pptx(root / "Company_Template.pptx")
        cls.port = _free_port()
        env = os.environ.copy()
        env.update({
            "APP_HOST": "127.0.0.1",
            "APP_PORT": str(cls.port),
            "APP_STORAGE_DIR": str(root / "storage"),
            "API_KEY": "compliance-key",
            "WEB_SEARCH_ENABLED": "false",
            "LLM_PROVIDER": "deterministic",
        })
        cls.process = subprocess.Popen([sys.executable, "-m", "app.main"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.time() + STARTUP_TIMEOUT_SECONDS
        while time.time() < deadline:
            try:
                status, _headers, _body = cls.request("GET", "/api/health")
                if status == 200:
                    return
            except OSError:
                time.sleep(0.2)
        raise RuntimeError("API server did not become ready")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.process.terminate()
        try:
            cls.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            cls.process.kill()
            cls.process.wait(timeout=5)
        cls.temp.cleanup()

    @classmethod
    def request(cls, method: str, path: str, body: bytes | None = None, headers: dict[str, str] | None = None) -> tuple[int, dict[str, str], bytes]:
        connection = HTTPConnection("127.0.0.1", cls.port, timeout=REQUEST_TIMEOUT_SECONDS)
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        result = (response.status, {key: value for key, value in response.getheaders()}, response.read())
        connection.close()
        return result

    def test_authenticated_browser_session_and_full_artifact_flow(self) -> None:
        status, headers, _ = self.request("GET", "/")
        self.assertEqual(status, 200)
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        session_headers = {"Cookie": cookie}

        unauthorized, _headers, _body = self.request("GET", "/api/uploads")
        self.assertEqual(unauthorized, 401)
        authorized, _headers, _body = self.request("GET", "/api/uploads", headers=session_headers)
        self.assertEqual(authorized, 200)

        before_payload = json.loads(_body)
        before_count = len(before_payload["uploads"])
        invalid_body, invalid_type = _multipart("rejected.txt", b"this is not a supported artifact")
        rejected, _headers, _body = self.request("POST", "/api/upload", invalid_body, {**session_headers, "Content-Type": invalid_type, "Content-Length": str(len(invalid_body))})
        self.assertEqual(rejected, 400)
        after_status, _headers, after_body = self.request("GET", "/api/uploads", headers=session_headers)
        self.assertEqual(after_status, 200)
        self.assertEqual(len(json.loads(after_body)["uploads"]), before_count)

        upload_ids = []
        for path in (self.doc, self.ppt):
            body, content_type = _multipart(path.name, path.read_bytes())
            uploaded, _headers, response_body = self.request("POST", "/api/upload", body, {**session_headers, "Content-Type": content_type, "Content-Length": str(len(body))})
            self.assertEqual(uploaded, 200)
            upload_ids.append(json.loads(response_body)["upload"]["upload_id"])

        chat_body = json.dumps({"message": "Create a research-backed proposal and 12-slide presentation", "upload_ids": upload_ids, "slide_count": 12}).encode("utf-8")
        run_status, _headers, run_body = self.request("POST", "/api/chat", chat_body, {**session_headers, "Content-Type": "application/json"})
        self.assertEqual(run_status, 200)
        run = json.loads(run_body)
        self.assertEqual(run["status"], "completed")
        self.assertEqual(len(run["artifacts"]), 2)
        doc_artifact = next(item for item in run["artifacts"] if item["file_type"] == "docx")

        artifact_status, _headers, artifact_body = self.request("GET", f"/api/artifacts/{doc_artifact['artifact_id']}", headers=session_headers)
        self.assertEqual(artifact_status, 200)
        self.assertTrue(json.loads(artifact_body)["versions"][-1]["lineage"]["run_id"] == run["run_id"])
        download_status, download_headers, download_body = self.request("GET", f"/api/artifacts/{doc_artifact['artifact_id']}/download", headers=session_headers)
        self.assertEqual(download_status, 200)
        self.assertEqual(download_headers["Content-Type"], "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        self.assertTrue(download_body.startswith(b"PK"))

        edit_body = json.dumps({"message": "Add an executive summary and competitive analysis section.", "artifact_id": doc_artifact["artifact_id"]}).encode("utf-8")
        edit_status, _headers, edit_response = self.request("POST", "/api/chat", edit_body, {**session_headers, "Content-Type": "application/json"})
        self.assertEqual(edit_status, 200)
        self.assertEqual(json.loads(edit_response)["artifacts"][0]["version"], 2)
        prior_status, _headers, prior_body = self.request("GET", f"/api/artifacts/{doc_artifact['artifact_id']}/download?version=1", headers=session_headers)
        self.assertEqual(prior_status, 200)
        self.assertTrue(prior_body.startswith(b"PK"))

        convert_body = json.dumps({"artifact_id": doc_artifact["artifact_id"], "target_format": "pptx"}).encode("utf-8")
        convert_status, _headers, convert_response = self.request("POST", "/api/convert", convert_body, {**session_headers, "Content-Type": "application/json"})
        self.assertEqual(convert_status, 200)
        converted = json.loads(convert_response)
        self.assertEqual(converted["file_type"], "pptx")
        self.assertTrue(converted["validation"]["passed"])
        conversion_run_status, _headers, conversion_run_body = self.request("GET", f"/api/runs/{converted['lineage']['run_id']}", headers=session_headers)
        self.assertEqual(conversion_run_status, 200)
        self.assertEqual(json.loads(conversion_run_body)["metadata"]["mode"], "conversion")

        ppt_artifact = next(item for item in run["artifacts"] if item["file_type"] == "pptx")
        reverse_body = json.dumps({"artifact_id": ppt_artifact["artifact_id"], "target_format": "docx"}).encode("utf-8")
        reverse_status, _headers, reverse_response = self.request("POST", "/api/convert", reverse_body, {**session_headers, "Content-Type": "application/json"})
        self.assertEqual(reverse_status, 200)
        reverse = json.loads(reverse_response)
        self.assertEqual(reverse["file_type"], "docx")
        self.assertTrue(reverse["validation"]["passed"])

        missing_status, _headers, _body = self.request("POST", "/api/convert", json.dumps({"artifact_id": "artifact_missing", "target_format": "pptx"}).encode("utf-8"), {**session_headers, "Content-Type": "application/json"})
        self.assertEqual(missing_status, 404)
        cors_status, cors_headers, _body = self.request("GET", "/api/health", headers={"Origin": "https://untrusted.example"})
        self.assertEqual(cors_status, 200)
        self.assertNotIn("Access-Control-Allow-Origin", cors_headers)


if __name__ == "__main__":
    unittest.main()

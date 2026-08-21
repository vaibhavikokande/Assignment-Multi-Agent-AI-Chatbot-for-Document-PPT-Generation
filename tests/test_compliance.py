from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.config import Settings, _load_dotenv
from app.content import OpenAICompatibleContentProvider, build_content_provider
from app.models import SourceCitation
from app.parsers import parse_file
from app.rag import EnterpriseKnowledgeBase, PineconeAdapter
from app.research import ResearchResult, WebSearchProvider
from samples.create_samples import create_sample_pptx


class _Response:
    def __init__(self, payload: dict) -> None:
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.payload


class ProviderContractTests(unittest.TestCase):
    def test_dotenv_loader_sets_missing_values_without_overriding_shell(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_path = Path(directory) / ".env"
            env_path.write_text("TAVILY_API_KEY=file-key\nLLM_API_URL='https://llm.example.test/v1'\nINVALID-KEY=ignored\n", encoding="utf-8")
            with patch.dict(os.environ, {"TAVILY_API_KEY": "shell-key"}, clear=True):
                _load_dotenv(env_path)
                self.assertEqual(os.environ["TAVILY_API_KEY"], "shell-key")
                self.assertEqual(os.environ["LLM_API_URL"], "https://llm.example.test/v1")
                self.assertNotIn("INVALID-KEY", os.environ)

    def test_json_web_provider_records_live_result(self) -> None:
        response = _Response({"results": [{"title": "Live result", "url": "https://example.com/live", "snippet": "A mocked provider response."}]})
        with patch("urllib.request.urlopen", return_value=response):
            result = WebSearchProvider(provider="json_api", api_url="https://search.example.test/search", api_key="secret").search("AI")
        self.assertEqual(result.provider, "json_web_api")
        self.assertIsNone(result.fallback_reason)
        self.assertEqual(result.sources[0].source_type, "web_api")

    def test_tavily_provider_posts_bearer_authenticated_live_result(self) -> None:
        response = _Response({"results": [{"title": "Tavily result", "url": "https://example.com/tavily", "content": "A mocked Tavily response."}]})
        with patch("urllib.request.urlopen", return_value=response) as mocked_urlopen:
            result = WebSearchProvider(provider="tavily", api_key="tvly-test-key").search("latest AI trends", limit=3)
        request = mocked_urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.tavily.com/search")
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.get_header("Authorization"), "Bearer tvly-test-key")
        self.assertEqual(json.loads((request.data or b"{}").decode("utf-8"))["max_results"], 3)
        self.assertEqual(result.provider, "tavily_live")
        self.assertIsNone(result.fallback_reason)
        self.assertEqual(result.sources[0].source_type, "tavily")

    def test_tavily_provider_records_missing_key_fallback(self) -> None:
        result = WebSearchProvider(provider="tavily").search("latest AI trends")
        self.assertEqual(result.provider, "deterministic_demo_fallback")
        self.assertEqual(result.fallback_reason, "TAVILY_API_KEY is not configured")

    def test_llm_provider_parses_structured_json(self) -> None:
        slides = [{"title": f"Slide {index}", "bullets": ["Evidence-led point"]} for index in range(11)]
        content = {"title": "Mocked", "subtitle": "Request", "executive_summary": "Summary", "sections": [{"heading": "One", "body": "Body", "bullets": ["Point"]}], "slides": slides, "claim_citations": []}
        response = _Response({"choices": [{"message": {"content": json.dumps(content)}}]})
        research = ResearchResult("AI", "json_web_api", [SourceCitation("Source", "https://example.com/source", "Snippet")], "Live")
        provider = OpenAICompatibleContentProvider("https://llm.example.test/v1", "secret", "model")
        with patch("urllib.request.urlopen", return_value=response):
            result = provider.generate("Request", [], research, [], 12)
        self.assertEqual(result.provider, "openai_compatible")
        self.assertEqual(len(result.content["slides"]), 11)
        self.assertEqual(result.content["sources"][0]["url"], "https://example.com/source")

    def test_misconfigured_optional_llm_falls_back_explicitly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = Settings(root_dir=root, storage_dir=root / "storage", llm_provider="openai_compatible")
            provider = build_content_provider(settings)
            result = provider.generate("Request", [], ResearchResult("AI", "offline", [], "offline"), [], 12)
        self.assertEqual(result.provider, "deterministic_fallback")
        self.assertIn("openai_compatible failed", result.fallback_reason or "")

    def test_pinecone_adapter_routes_upsert_and_query(self) -> None:
        adapter = PineconeAdapter(enabled=True, api_key="secret", index_host="https://index.example.test")
        requests: list[tuple[str, dict]] = []

        def fake_request(path: str, payload: dict) -> dict:
            requests.append((path, payload))
            return {"matches": [{"id": "doc#1", "score": 0.91, "metadata": {"title": "Remote", "text": "Remote enterprise context", "source_type": "enterprise_file"}}]} if path == "/query" else {}

        with patch.object(adapter, "_request", side_effect=fake_request):
            adapter.upsert([{"document_id": "doc#1", "title": "Remote", "text": "Remote enterprise context", "source_type": "enterprise_file"}])
            hits = adapter.retrieve("enterprise context")
        self.assertEqual(requests[0][0], "/vectors/upsert")
        self.assertEqual(requests[1][0], "/query")
        self.assertEqual(hits[0]["source_type"], "enterprise_file")

    def test_pinecone_adapter_sends_data_plane_version_header(self) -> None:
        adapter = PineconeAdapter(enabled=True, api_key="secret", index_host="https://index.example.test")
        with patch("urllib.request.urlopen", return_value=_Response({})) as mocked_urlopen:
            adapter._request("/query", {"vector": []})
        request = mocked_urlopen.call_args.args[0]
        headers = {name.lower(): value for name, value in request.header_items()}
        self.assertEqual(request.full_url, "https://index.example.test/query")
        self.assertEqual(headers["api-key"], "secret")
        self.assertEqual(headers["x-pinecone-api-version"], "2026-04")

    def test_integrated_pinecone_adapter_routes_text_records_and_search(self) -> None:
        adapter = PineconeAdapter(
            enabled=True,
            api_key="secret",
            index_host="https://index.example.test",
            namespace="__default__",
            mode="integrated",
            text_field="text",
        )
        requests: list[tuple[str, object, str]] = []

        def fake_request(path: str, payload: object, content_type: str = "application/json") -> dict:
            requests.append((path, payload, content_type))
            if path.endswith("/search"):
                return {"result": {"hits": [{"_id": "doc#1", "_score": 0.91, "fields": {"title": "Remote", "text": "Remote enterprise context", "source_type": "enterprise_file"}}]}}
            return {}

        with patch.object(adapter, "_request", side_effect=fake_request):
            adapter.upsert([{"document_id": "doc#1", "title": "Remote", "text": "Remote enterprise context", "source_type": "enterprise_file"}])
            hits = adapter.retrieve("enterprise context")
        self.assertEqual(requests[0][0], "/records/namespaces/__default__/upsert")
        self.assertEqual(requests[0][2], "application/x-ndjson")
        self.assertEqual(requests[0][1], [{"_id": "doc#1", "text": "Remote enterprise context", "title": "Remote", "source_type": "enterprise_file"}])
        self.assertEqual(requests[1][0], "/records/namespaces/__default__/search")
        self.assertEqual(requests[1][1], {"query": {"inputs": {"text": "enterprise context"}, "top_k": 4}, "fields": ["title", "source_type", "text"]})
        self.assertEqual(hits[0]["source_type"], "enterprise_file")
        self.assertEqual(adapter.provider_name, "pinecone_integrated")

    def test_integrated_pinecone_adapter_encodes_ndjson_records(self) -> None:
        adapter = PineconeAdapter(enabled=True, api_key="secret", index_host="https://index.example.test", mode="integrated")
        with patch("urllib.request.urlopen", return_value=_Response({})) as mocked_urlopen:
            adapter._request("/records/namespaces/__default__/upsert", [{"_id": "doc#1", "chunk_text": "Remote context"}], "application/x-ndjson")
        request = mocked_urlopen.call_args.args[0]
        headers = {name.lower(): value for name, value in request.header_items()}
        self.assertEqual(headers["content-type"], "application/x-ndjson")
        self.assertEqual((request.data or b"").decode("utf-8"), '{"_id":"doc#1","chunk_text":"Remote context"}\n')

    def test_enterprise_file_is_ingested_into_local_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "enterprise_context.md"
            path.write_text("Deployment controls require human approval and measurable value.", encoding="utf-8")
            knowledge = EnterpriseKnowledgeBase(Path(directory))
            hits = knowledge.retrieve("deployment controls human approval")
        self.assertTrue(any(hit["source_type"] == "enterprise_file" for hit in hits))


@unittest.skipUnless(shutil.which("tesseract") and shutil.which("pdftoppm"), "Tesseract and pdftoppm are required for OCR acceptance")
class OCRComplianceTests(unittest.TestCase):
    def test_image_and_scanned_pdf_produce_ocr_text(self) -> None:
        from PIL import Image, ImageDraw, ImageFont

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image_path = root / "ocr.png"
            font_path = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
            font = ImageFont.truetype(str(font_path), 42) if font_path.exists() else None
            image = Image.new("RGB", (1200, 240), "white")
            ImageDraw.Draw(image).text((40, 70), "Enterprise OCR acceptance test", fill="black", font=font)
            image.save(image_path)
            image_profile = parse_file(image_path)
            pdf_path = root / "ocr.pdf"
            image.save(pdf_path, format="PDF")
            pdf_profile = parse_file(pdf_path)
        self.assertEqual(image_profile.ocr_status, "ok")
        self.assertTrue(image_profile.text)
        self.assertEqual(pdf_profile.ocr_status, "ok")
        self.assertTrue(pdf_profile.text)


@unittest.skipUnless(shutil.which("soffice"), "LibreOffice is required for legacy PPT acceptance")
class LegacyPPTComplianceTests(unittest.TestCase):
    def test_legacy_ppt_is_converted_and_profiled(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = create_sample_pptx(root / "source.pptx")
            result = subprocess.run([shutil.which("soffice") or "soffice", "--headless", "--convert-to", "ppt", "--outdir", str(root), str(source)], capture_output=True, text=True, timeout=60)
            legacy = root / "source.ppt"
            if result.returncode != 0 or not legacy.exists():
                self.skipTest("LibreOffice could not create a legacy PPT in this environment")
            profile = parse_file(legacy)
        self.assertEqual(profile.file_type, "ppt")
        self.assertEqual(profile.extraction_status, "converted_to_pptx")


class UIContractTests(unittest.TestCase):
    def test_browser_surface_contains_required_workflow_controls(self) -> None:
        static_dir = Path(__file__).parents[1] / "app" / "static"
        html = (static_dir / "index.html").read_text(encoding="utf-8")
        javascript = (static_dir / "app.js").read_text(encoding="utf-8")
        for marker in ("file-input", "run-button", "artifact-select", "edit-button"):
            self.assertIn(marker, html)
        for endpoint in ("/api/upload", "/api/chat", "/api/artifacts", "/api/health"):
            self.assertIn(endpoint, javascript)


if __name__ == "__main__":
    unittest.main()

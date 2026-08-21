from __future__ import annotations

import hashlib
import json
import math
import re
import urllib.parse
import urllib.request
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]{2,}", text.lower())


def _chunks(text: str, chunk_size: int = 1200, overlap: int = 120) -> list[str]:
    clean = " ".join(text.split())
    if not clean:
        return []
    chunks = []
    start = 0
    while start < len(clean):
        end = min(len(clean), start + chunk_size)
        chunks.append(clean[start:end])
        if end == len(clean):
            break
        start = max(start + 1, end - overlap)
    return chunks


@dataclass
class RetrievalHit:
    document_id: str
    title: str
    text: str
    score: float
    source_type: str = "enterprise"

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "title": self.title,
            "text": self.text,
            "score": round(self.score, 4),
            "source_type": self.source_type,
        }


class LocalVectorStore:
    """Deterministic local retrieval used when no remote vector provider is configured."""

    def __init__(self) -> None:
        self.documents: list[dict[str, str]] = []

    def add(self, document_id: str, title: str, text: str, source_type: str = "enterprise") -> None:
        self.documents.append({"document_id": document_id, "title": title, "text": text, "source_type": source_type})

    def search(self, query: str, limit: int = 4) -> list[RetrievalHit]:
        query_tokens = Counter(_tokens(query))
        if not query_tokens:
            return []
        scored: list[RetrievalHit] = []
        for document in self.documents:
            doc_tokens = Counter(_tokens(document["text"]))
            common = set(query_tokens).intersection(doc_tokens)
            numerator = sum(query_tokens[token] * doc_tokens[token] for token in common)
            denominator = math.sqrt(sum(value * value for value in query_tokens.values())) * math.sqrt(sum(value * value for value in doc_tokens.values()))
            score = numerator / denominator if denominator else 0.0
            if score > 0:
                scored.append(RetrievalHit(score=score, **document))
        return sorted(scored, key=lambda hit: hit.score, reverse=True)[:limit]


class HashEmbedder:
    """Small deterministic embedder for a credential-optional Pinecone contract."""

    def __init__(self, dimension: int = 128) -> None:
        self.dimension = dimension

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        for token in _tokens(text):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimension
            sign = 1.0 if digest[4] % 2 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [round(value / norm, 8) for value in vector]


class PineconeAdapter:
    """Pinecone data-plane adapter for external-vector and integrated-embedding indexes."""

    def __init__(
        self,
        enabled: bool = False,
        api_key: str | None = None,
        index_host: str | None = None,
        namespace: str = "__default__",
        api_version: str = "2026-04",
        mode: str = "vectors",
        text_field: str = "chunk_text",
        timeout: int = 10,
    ) -> None:
        self.enabled = enabled and bool(api_key and index_host)
        self.api_key = api_key
        self.index_host = index_host.rstrip("/") if index_host else None
        self.namespace = namespace
        self.api_version = api_version
        self.mode = mode.strip().lower()
        if self.mode not in {"vectors", "integrated"}:
            raise ValueError("PINECONE_MODE must be 'vectors' or 'integrated'")
        self.text_field = text_field.strip() or "chunk_text"
        self.timeout = timeout
        self.embedder = HashEmbedder()

    @property
    def provider_name(self) -> str:
        return "pinecone_integrated" if self.mode == "integrated" else "pinecone"

    def _request(self, path: str, payload: Any, content_type: str = "application/json") -> dict[str, Any]:
        if not self.enabled or not self.index_host or not self.api_key:
            raise RuntimeError("Pinecone adapter is not configured")
        if content_type == "application/x-ndjson":
            body = ("\n".join(json.dumps(record, separators=(",", ":")) for record in payload) + "\n").encode("utf-8")
        else:
            body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.index_host}{path}",
            data=body,
            headers={
                "Api-Key": self.api_key,
                "Content-Type": content_type,
                "Accept": "application/json",
                "X-Pinecone-Api-Version": self.api_version,
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8", "ignore"))

    def upsert(self, documents: list[dict[str, str]]) -> None:
        if not self.enabled or not documents:
            return
        if self.mode == "integrated":
            records = [
                {
                    "_id": document["document_id"],
                    self.text_field: document["text"],
                    "title": document["title"],
                    "source_type": document["source_type"],
                }
                for document in documents
            ]
            path = f"/records/namespaces/{urllib.parse.quote(self.namespace, safe='')}/upsert"
            for start in range(0, len(records), 96):
                self._request(path, records[start:start + 96], "application/x-ndjson")
            return
        vectors = [
            {
                "id": document["document_id"],
                "values": self.embedder.embed(document["text"]),
                "metadata": {"title": document["title"], "text": document["text"], "source_type": document["source_type"]},
            }
            for document in documents
        ]
        self._request("/vectors/upsert", {"namespace": self.namespace, "vectors": vectors})

    def retrieve(self, query: str, limit: int = 4) -> list[dict[str, Any]]:
        if self.mode == "integrated":
            path = f"/records/namespaces/{urllib.parse.quote(self.namespace, safe='')}/search"
            payload = self._request(
                path,
                {
                    "query": {"inputs": {"text": query}, "top_k": limit},
                    "fields": ["title", "source_type", self.text_field],
                },
            )
            hits = []
            for match in payload.get("result", {}).get("hits", []):
                fields = match.get("fields", {})
                hits.append(RetrievalHit(
                    document_id=str(match.get("_id", "pinecone-match")),
                    title=str(fields.get("title", "Enterprise knowledge")),
                    text=str(fields.get(self.text_field, "")),
                    score=float(match.get("_score", 0.0)),
                    source_type=str(fields.get("source_type", "enterprise")),
                ).to_dict())
            return hits
        payload = self._request("/query", {"namespace": self.namespace, "vector": self.embedder.embed(query), "topK": limit, "includeMetadata": True})
        hits = []
        for match in payload.get("matches", []):
            metadata = match.get("metadata", {})
            hits.append(RetrievalHit(
                document_id=str(match.get("id", "pinecone-match")),
                title=str(metadata.get("title", "Enterprise knowledge")),
                text=str(metadata.get("text", "")),
                score=float(match.get("score", 0.0)),
                source_type=str(metadata.get("source_type", "enterprise")),
            ).to_dict())
        return hits


class EnterpriseKnowledgeBase:
    def __init__(
        self,
        enterprise_kb_dir: Path | None = None,
        pinecone_api_key: str | None = None,
        pinecone_index_host: str | None = None,
        pinecone_namespace: str = "__default__",
        pinecone_api_version: str = "2026-04",
        pinecone_mode: str = "vectors",
        pinecone_text_field: str = "chunk_text",
    ) -> None:
        self.store = LocalVectorStore()
        self.remote = PineconeAdapter(
            bool(pinecone_api_key and pinecone_index_host),
            pinecone_api_key,
            pinecone_index_host,
            pinecone_namespace,
            pinecone_api_version,
            pinecone_mode,
            pinecone_text_field,
        )
        self.last_provider = "local"
        self.last_error: str | None = None
        self._add_document("kb-company", "Company knowledge base", "Our company helps enterprise teams adopt secure generative AI. We prioritize measurable productivity, governance, interoperability, and responsible deployment.", "enterprise")
        self._add_document("kb-offering", "Company offering brief", "The flagship offering combines discovery workshops, workflow automation, model evaluation, knowledge retrieval, and change management for regulated organizations.", "enterprise")
        self._add_document("kb-positioning", "Company positioning", "Our positioning is practical, executive-friendly, evidence-led, and focused on reducing time to value without compromising data controls.", "enterprise")
        if enterprise_kb_dir:
            self.ingest_directory(enterprise_kb_dir)

    def _add_document(self, document_id: str, title: str, text: str, source_type: str) -> None:
        documents = []
        for index, chunk in enumerate(_chunks(text)):
            document = {"document_id": f"{document_id}#chunk-{index + 1}", "title": title, "text": chunk, "source_type": source_type}
            self.store.add(**document)
            documents.append(document)
        if self.remote.enabled:
            try:
                self.remote.upsert(documents)
            except Exception as exc:
                self.last_error = f"Pinecone upsert failed: {type(exc).__name__}"

    def ingest_profile(self, profile: dict[str, Any]) -> None:
        text = profile.get("text", "").strip()
        if text:
            self._add_document(profile.get("profile_id", "uploaded-profile"), profile.get("file_name", "Uploaded file"), text, "uploaded")

    def ingest_directory(self, directory: Path) -> None:
        directory = Path(directory)
        if not directory.exists():
            return
        for path in sorted(directory.rglob("*")):
            if path.is_file() and path.suffix.lower() in {".md", ".txt"}:
                self._add_document(f"kb-file-{path.stem}", path.name, path.read_text(encoding="utf-8", errors="ignore"), "enterprise_file")

    def retrieve(self, query: str, limit: int = 4) -> list[dict[str, Any]]:
        self.last_error = None
        if self.remote.enabled:
            try:
                remote_hits = self.remote.retrieve(query, limit)
                if remote_hits:
                    self.last_provider = self.remote.provider_name
                    return remote_hits
                self.last_error = "Pinecone returned no matches; local retrieval used"
            except Exception as exc:
                self.last_error = f"Pinecone query failed: {type(exc).__name__}"
        self.last_provider = "local"
        return [hit.to_dict() for hit in self.store.search(query, limit)]

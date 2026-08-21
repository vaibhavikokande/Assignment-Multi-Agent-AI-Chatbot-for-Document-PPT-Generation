from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


@dataclass
class SourceCitation:
    title: str
    url: str
    snippet: str
    source_type: str = "web"
    retrieved_at: str = field(default_factory=utc_now)


@dataclass
class DocumentProfile:
    profile_id: str
    file_name: str
    file_type: str
    text: str
    page_count: int = 0
    slide_count: int = 0
    paragraph_count: int = 0
    table_count: int = 0
    image_count: int = 0
    style: dict[str, Any] = field(default_factory=dict)
    sections: list[dict[str, Any]] = field(default_factory=list)
    extraction_status: str = "ok"
    ocr_status: str = "not_applicable"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AgentStep:
    agent: str
    status: str
    summary: str
    started_at: str = field(default_factory=utc_now)
    finished_at: str = field(default_factory=utc_now)
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class ArtifactVersion:
    artifact_id: str
    version: int
    file_name: str
    file_type: str
    relative_path: str
    request: str
    content: dict[str, Any]
    profile: dict[str, Any]
    citations: list[dict[str, Any]]
    trace_id: str
    created_at: str = field(default_factory=utc_now)
    validation: dict[str, Any] = field(default_factory=dict)
    lineage: dict[str, Any] = field(default_factory=dict)


@dataclass
class RunRecord:
    run_id: str
    request: str
    status: str
    steps: list[dict[str, Any]] = field(default_factory=list)
    sources: list[dict[str, Any]] = field(default_factory=list)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    retrieval: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now)
    completed_at: str | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def to_jsonable(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: to_jsonable(item) for key, item in value.items()}
    return value

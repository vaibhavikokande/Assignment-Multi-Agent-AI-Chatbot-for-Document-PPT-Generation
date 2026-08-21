from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from .config import Settings
from .models import ArtifactVersion, RunRecord, new_id, to_jsonable, utc_now


class ArtifactRepository:
    """JSON-backed local repository; the single owner of uploads, runs, and versions."""

    def __init__(self, settings: Settings):
        self.settings = settings
        settings.ensure_directories()
        if not settings.registry_path.exists():
            self._write_registry({"uploads": [], "artifacts": {}, "runs": {}})

    def _read_registry(self) -> dict[str, Any]:
        try:
            return json.loads(self.settings.registry_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, FileNotFoundError):
            return {"uploads": [], "artifacts": {}, "runs": {}}

    def _write_registry(self, registry: dict[str, Any]) -> None:
        temporary = self.settings.registry_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(registry, indent=2), encoding="utf-8")
        temporary.replace(self.settings.registry_path)

    def save_upload(self, file_name: str, data: bytes) -> dict[str, Any]:
        upload_id = new_id("upload")
        safe_name = Path(file_name).name or "upload.bin"
        stored_name = f"{upload_id}_{safe_name}"
        destination = self.settings.upload_dir / stored_name
        destination.write_bytes(data)
        record = {
            "upload_id": upload_id,
            "file_name": safe_name,
            "relative_path": str(destination.relative_to(self.settings.storage_dir)),
            "bytes": len(data),
            "created_at": utc_now(),
        }
        registry = self._read_registry()
        registry.setdefault("uploads", []).append(record)
        self._write_registry(registry)
        return record

    def get_upload(self, upload_id: str) -> dict[str, Any] | None:
        return next((item for item in self._read_registry().get("uploads", []) if item["upload_id"] == upload_id), None)

    def list_uploads(self) -> list[dict[str, Any]]:
        return list(reversed(self._read_registry().get("uploads", [])))

    def upload_path(self, upload_id: str) -> Path:
        record = self.get_upload(upload_id)
        if not record:
            raise KeyError(f"Unknown upload: {upload_id}")
        return self.settings.storage_dir / record["relative_path"]

    def save_run(self, run: RunRecord | dict[str, Any]) -> dict[str, Any]:
        payload = to_jsonable(run)
        registry = self._read_registry()
        registry.setdefault("runs", {})[payload["run_id"]] = payload
        self._write_registry(registry)
        (self.settings.run_dir / f"{payload['run_id']}.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return payload

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        return self._read_registry().get("runs", {}).get(run_id)

    def register_artifact(self, artifact: ArtifactVersion | dict[str, Any], file_path: Path) -> dict[str, Any]:
        payload = to_jsonable(artifact)
        payload["relative_path"] = str(file_path.relative_to(self.settings.storage_dir))
        registry = self._read_registry()
        bucket = registry.setdefault("artifacts", {}).setdefault(payload["artifact_id"], {"versions": []})
        bucket["versions"].append(payload)
        bucket["current_version"] = payload["version"]
        self._write_registry(registry)
        return payload

    def get_artifact(self, artifact_id: str) -> dict[str, Any] | None:
        return self._read_registry().get("artifacts", {}).get(artifact_id)

    def list_artifacts(self) -> list[dict[str, Any]]:
        registry = self._read_registry()
        output = []
        for artifact_id, bucket in registry.get("artifacts", {}).items():
            versions = bucket.get("versions", [])
            if versions:
                current = versions[-1].copy()
                current["artifact_id"] = artifact_id
                current["version_count"] = len(versions)
                output.append(current)
        return sorted(output, key=lambda item: item.get("created_at", ""), reverse=True)

    def artifact_path(self, artifact_id: str, version: int | None = None) -> Path:
        bucket = self.get_artifact(artifact_id)
        if not bucket:
            raise KeyError(f"Unknown artifact: {artifact_id}")
        versions = bucket.get("versions", [])
        target = versions[-1] if version is None else next((item for item in versions if item["version"] == version), None)
        if not target:
            raise KeyError(f"Unknown version {version} for artifact {artifact_id}")
        return self.settings.storage_dir / target["relative_path"]

    def current_version(self, artifact_id: str) -> dict[str, Any]:
        bucket = self.get_artifact(artifact_id)
        if not bucket or not bucket.get("versions"):
            raise KeyError(f"Unknown artifact: {artifact_id}")
        return bucket["versions"][-1]

    def create_artifact_id(self) -> str:
        return new_id("artifact")

    def create_run_id(self) -> str:
        return new_id("run")

    def create_artifact_path(self, artifact_id: str, version: int, file_name: str) -> Path:
        suffix = Path(file_name).suffix.lower() or ".bin"
        destination = self.settings.artifact_dir / f"{artifact_id}_v{version}{suffix}"
        destination.parent.mkdir(parents=True, exist_ok=True)
        return destination

    def copy_artifact(self, artifact_id: str, destination: Path, version: int | None = None) -> Path:
        shutil.copy2(self.artifact_path(artifact_id, version), destination)
        return destination

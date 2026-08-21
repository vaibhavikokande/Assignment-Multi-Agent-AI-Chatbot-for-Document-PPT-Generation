from __future__ import annotations

from pathlib import Path
from typing import Any

from .content import build_content_provider
from .editing import apply_edit
from .generators import content_from_profile, generate_docx, generate_pptx
from .models import AgentStep, ArtifactVersion, DocumentProfile, RunRecord, to_jsonable, utc_now
from .parsers import parse_file, summarize_profile
from .rag import EnterpriseKnowledgeBase
from .research import ResearchResult, WebSearchProvider
from .repository import ArtifactRepository
from .validation import validate_artifact


class TraceRecorder:
    def __init__(self) -> None:
        self.steps: list[dict[str, Any]] = []

    def record(self, agent: str, summary: str, details: dict[str, Any] | None = None, status: str = "completed") -> None:
        self.steps.append(to_jsonable(AgentStep(agent=agent, status=status, summary=summary, details=details or {})))


class TemplateAnalysisAgent:
    name = "TemplateAnalysisAgent"

    def run(self, upload_records: list[dict[str, Any]], repository: ArtifactRepository, knowledge_base: EnterpriseKnowledgeBase, trace: TraceRecorder) -> list[dict[str, Any]]:
        profiles: list[dict[str, Any]] = []
        for record in upload_records:
            profile = parse_file(repository.settings.storage_dir / record["relative_path"], record["file_name"], repository.settings.ocr_enabled)
            profile_payload = profile.to_dict()
            profile_payload["_source_path"] = str(repository.settings.storage_dir / record["relative_path"])
            profiles.append(profile_payload)
            knowledge_base.ingest_profile(profile_payload)
        trace.record(
            self.name,
            f"Analyzed {len(profiles)} uploaded template(s)",
            {"profiles": [summarize_profile(DocumentProfile(**{key: value for key, value in profile.items() if key in DocumentProfile.__dataclass_fields__})) for profile in profiles]},
        )
        return profiles


class ResearchAgent:
    name = "ResearchAgent"

    def __init__(self, provider: WebSearchProvider) -> None:
        self.provider = provider

    def run(self, query: str, trace: TraceRecorder) -> ResearchResult:
        result = self.provider.search(query, limit=5)
        trace.record(
            self.name,
            result.summary,
            {"provider": result.provider, "source_count": len(result.sources), "fallback_reason": result.fallback_reason},
        )
        return result


class RetrievalAgent:
    name = "RetrievalAgent"

    def run(self, query: str, knowledge_base: EnterpriseKnowledgeBase, trace: TraceRecorder) -> list[dict[str, Any]]:
        hits = knowledge_base.retrieve(query)
        trace.record(
            self.name,
            f"Retrieved {len(hits)} enterprise context item(s)",
            {"hits": hits, "provider": knowledge_base.last_provider, "fallback_reason": knowledge_base.last_error},
        )
        return hits


class ContentAgent:
    name = "ContentAgent"

    def __init__(self, provider: Any) -> None:
        self.provider = provider

    def run(self, request: str, profiles: list[dict[str, Any]], research: ResearchResult, retrieval: list[dict[str, Any]], trace: TraceRecorder, slide_count: int = 12) -> dict[str, Any]:
        result = self.provider.generate(request, profiles, research, retrieval, slide_count)
        trace.record(
            self.name,
            "Created a structured proposal and slide outline",
            {
                "provider": result.provider,
                "fallback_reason": result.fallback_reason,
                "section_count": len(result.content.get("sections", [])),
                "slide_count": len(result.content.get("slides", [])) + 1,
            },
        )
        return result.content


class ValidationAgent:
    name = "ValidationAgent"

    def run(self, artifact_path: Path, file_type: str, trace: TraceRecorder, expected_slides: int | None = None, profile: dict[str, Any] | None = None) -> dict[str, Any]:
        report = validate_artifact(artifact_path, file_type, expected_slides, profile)
        trace.record(self.name, "Validated generated artifact" if report["passed"] else "Artifact validation found issues", report, "completed" if report["passed"] else "warning")
        return report


class SupervisorAgent:
    name = "SupervisorAgent"

    def __init__(self, repository: ArtifactRepository, web_search_enabled: bool | None = None) -> None:
        self.repository = repository
        settings = repository.settings
        enabled = settings.web_search_enabled if web_search_enabled is None else web_search_enabled
        self.knowledge_base = EnterpriseKnowledgeBase(
            settings.enterprise_kb_dir,
            settings.pinecone_api_key,
            settings.pinecone_index_host,
            settings.pinecone_namespace,
            settings.pinecone_api_version,
            settings.pinecone_mode,
            settings.pinecone_text_field,
        )
        self.research_agent = ResearchAgent(
            WebSearchProvider(
                enabled,
                provider=settings.web_search_provider,
                api_url=settings.web_search_api_url,
                api_key=settings.tavily_api_key if settings.web_search_provider == "tavily" else settings.web_search_api_key,
            )
        )
        self.template_agent = TemplateAnalysisAgent()
        self.retrieval_agent = RetrievalAgent()
        self.content_agent = ContentAgent(build_content_provider(settings))
        self.validation_agent = ValidationAgent()

    def _register_generated(
        self,
        artifact_id: str,
        version: int,
        file_type: str,
        request: str,
        content: dict[str, Any],
        profile: dict[str, Any],
        sources: list[dict[str, Any]],
        trace_id: str,
        expected_slides: int | None,
        trace: TraceRecorder,
        lineage: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        file_name = "generated-proposal.docx" if file_type == "docx" else "generated-presentation.pptx"
        output_path = self.repository.create_artifact_path(artifact_id, version, file_name)
        source_path = Path(profile.get("_source_path", "")) if profile.get("_source_path") else None
        if file_type == "docx":
            trace.record("DocumentGenerationAgent", "Generated a native editable DOCX artifact", {"artifact_id": artifact_id, "version": version})
            generate_docx(content, profile, output_path, source_path if source_path and source_path.suffix.lower() == ".docx" and source_path.exists() else None)
        else:
            trace.record("PPTGenerationAgent", "Generated a native editable PPTX artifact", {"artifact_id": artifact_id, "version": version, "expected_slides": expected_slides})
            generate_pptx(content, profile, output_path, source_path if source_path and source_path.suffix.lower() == ".pptx" and source_path.exists() else None)
        validation = self.validation_agent.run(output_path, file_type, trace, expected_slides, profile)
        artifact = ArtifactVersion(
            artifact_id,
            version,
            file_name,
            file_type,
            str(output_path.relative_to(self.repository.settings.storage_dir)),
            request,
            content,
            profile,
            sources,
            trace_id,
            validation=validation,
            lineage=lineage or {"run_id": trace_id},
        )
        return self.repository.register_artifact(artifact, output_path)

    def run(self, request: str, upload_ids: list[str] | None = None, edit_artifact_id: str | None = None, slide_count: int = 12) -> dict[str, Any]:
        run_id = self.repository.create_run_id()
        trace = TraceRecorder()
        trace.record(self.name, "Accepted request and selected the document/PPT workflow", {"request": request})
        run = RunRecord(run_id, request, "running")
        try:
            if edit_artifact_id:
                current = self.repository.current_version(edit_artifact_id)
                research = self.research_agent.run(request, trace) if any(token in request.lower() for token in ("latest", "web", "refresh", "update")) else ResearchResult(request, "not_requested", [], "No new research requested for this edit")
                content, changes = apply_edit(current["content"], request, [to_jsonable(source) for source in research.sources])
                version = int(current["version"]) + 1
                profile = dict(current["profile"])
                profile["_source_path"] = str(self.repository.artifact_path(edit_artifact_id, int(current["version"])))
                run.metadata = {
                    "mode": "edit",
                    "source_artifact_id": edit_artifact_id,
                    "source_version": current["version"],
                    "research_provider": research.provider,
                    "research_fallback_reason": research.fallback_reason,
                }
                artifact = self._register_generated(
                    edit_artifact_id,
                    version,
                    current["file_type"],
                    request,
                    content,
                    profile,
                    [to_jsonable(source) for source in research.sources] or current.get("citations", []),
                    run_id,
                    slide_count if current["file_type"] == "pptx" else None,
                    trace,
                    {"run_id": run_id, "mode": "edit", "source_artifact_id": edit_artifact_id, "source_version": current["version"]},
                )
                trace.record("EditingAgent", "; ".join(changes), {"artifact_id": edit_artifact_id, "version": version})
                run.status = "completed"
                run.artifacts = [artifact]
                run.sources = artifact.get("citations", [])
                run.steps = trace.steps
                run.completed_at = utc_now()
                return self.repository.save_run(run)

            records = [self.repository.get_upload(upload_id) for upload_id in (upload_ids or [])]
            records = [record for record in records if record]
            profiles = self.template_agent.run(records, self.repository, self.knowledge_base, trace) if records else []
            research = self.research_agent.run(request or "latest Generative AI trends", trace)
            retrieval = self.retrieval_agent.run(request, self.knowledge_base, trace)
            content = self.content_agent.run(request, profiles, research, retrieval, trace, slide_count)
            run.metadata = {
                "mode": "generation",
                "research_provider": research.provider,
                "research_fallback_reason": research.fallback_reason,
                "retrieval_provider": self.knowledge_base.last_provider,
                "retrieval_fallback_reason": self.knowledge_base.last_error,
                "content_provider": content.get("content_provider"),
                "content_fallback_reason": content.get("content_fallback_reason"),
            }
            doc_profile = next((profile for profile in profiles if profile["file_type"] == "docx"), profiles[0] if profiles else {"style": {}})
            ppt_profile = next((profile for profile in profiles if profile["file_type"] in {"pptx", "ppt"}), profiles[0] if profiles else {"style": {}})
            doc_id, ppt_id = self.repository.create_artifact_id(), self.repository.create_artifact_id()
            source_lineage = {"run_id": run_id, "mode": "generation", "source_upload_ids": upload_ids or [], "providers": run.metadata}
            doc_artifact = self._register_generated(doc_id, 1, "docx", request, content, doc_profile, [to_jsonable(source) for source in research.sources], run_id, None, trace, source_lineage)
            ppt_artifact = self._register_generated(ppt_id, 1, "pptx", request, content, ppt_profile, [to_jsonable(source) for source in research.sources], run_id, slide_count, trace, source_lineage)
            run.status = "completed"
            run.sources = [to_jsonable(source) for source in research.sources]
            run.retrieval = retrieval
            run.artifacts = [doc_artifact, ppt_artifact]
            run.steps = trace.steps
            run.completed_at = utc_now()
            return self.repository.save_run(run)
        except Exception as exc:
            trace.record("SupervisorAgent", "Workflow failed", {"error": str(exc)}, "failed")
            run.status = "failed"
            run.error = str(exc)
            run.steps = trace.steps
            run.completed_at = utc_now()
            return self.repository.save_run(run)


def convert_artifact(repository: ArtifactRepository, artifact_id: str, target_format: str, request: str = "Convert artifact") -> dict[str, Any]:
    current = repository.current_version(artifact_id)
    source_path = repository.artifact_path(artifact_id)
    source_profile = parse_file(source_path, current["file_name"], repository.settings.ocr_enabled)
    content = content_from_profile(source_profile, request)
    new_type = target_format.lower().lstrip(".")
    if new_type not in {"docx", "pptx"}:
        raise ValueError("target_format must be docx or pptx")
    new_id_value = repository.create_artifact_id()
    run_id = repository.create_run_id()
    trace = TraceRecorder()
    trace.record("ConversionAgent", f"Converted {current['file_type']} to {new_type}", {"source_artifact_id": artifact_id})
    supervisor = SupervisorAgent(repository, web_search_enabled=False)
    profile = source_profile.to_dict()
    profile["_source_path"] = str(source_path)
    run = RunRecord(
        run_id,
        request,
        "running",
        metadata={"mode": "conversion", "source_artifact_id": artifact_id, "source_version": current["version"], "target_format": new_type},
    )
    try:
        artifact = supervisor._register_generated(
            new_id_value,
            1,
            new_type,
            request,
            content,
            profile,
            [],
            run_id,
            12 if new_type == "pptx" else None,
            trace,
            {"run_id": run_id, "mode": "conversion", "source_artifact_id": artifact_id, "source_version": current["version"], "target_format": new_type},
        )
        run.status = "completed"
        run.artifacts = [artifact]
        run.steps = trace.steps
        run.completed_at = utc_now()
        repository.save_run(run)
        return artifact
    except Exception as exc:
        trace.record("ConversionAgent", "Conversion failed", {"error": str(exc)}, "failed")
        run.status = "failed"
        run.error = str(exc)
        run.steps = trace.steps
        run.completed_at = utc_now()
        repository.save_run(run)
        raise

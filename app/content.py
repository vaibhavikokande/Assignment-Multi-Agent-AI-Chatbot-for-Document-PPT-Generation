from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from typing import Any

from .models import to_jsonable
from .research import ResearchResult


@dataclass
class ContentResult:
    content: dict[str, Any]
    provider: str
    fallback_reason: str | None = None


def _source_dicts(research: ResearchResult) -> list[dict[str, Any]]:
    return [to_jsonable(source) for source in research.sources]


class DeterministicContentProvider:
    provider_name = "deterministic_fallback"

    def generate(
        self,
        request: str,
        profiles: list[dict[str, Any]],
        research: ResearchResult,
        retrieval: list[dict[str, Any]],
        slide_count: int = 12,
    ) -> ContentResult:
        title = "Generative AI Trends Proposal"
        enterprise_hits = [hit for hit in retrieval if hit.get("source_type") == "enterprise"]
        enterprise_context = (
            enterprise_hits[0]
            if enterprise_hits
            else (retrieval[0] if retrieval else {"text": "Enterprise teams need measurable, governed adoption pathways."})
        )["text"]
        source_dicts = _source_dicts(research)
        sections = [
            {
                "heading": "Market Context",
                "body": "Generative AI is moving from experimentation into governed workflow redesign, with value depending on reliable evidence, usable interfaces, and change management.",
                "bullets": [
                    "Model capability and adoption continue to expand",
                    "Enterprise value shifts from demos to repeatable workflows",
                    "Evaluation, security, and provenance are becoming operating requirements",
                ],
            },
            {
                "heading": "Enterprise Opportunity",
                "body": enterprise_context,
                "bullets": [
                    "Automate high-friction knowledge work",
                    "Use retrieval to ground domain-specific decisions",
                    "Measure time saved, quality, adoption, and risk",
                ],
            },
            {
                "heading": "Research-Led Operating Model",
                "body": "The POC combines live research, enterprise knowledge, structured content planning, and deterministic validation before producing a file.",
                "bullets": [
                    "Research Agent brings in current external signals",
                    "Retrieval Agent adds company context",
                    "Validation Agent checks content and artifact structure",
                ],
            },
            {
                "heading": "Priority Use Cases",
                "body": "Start with workflows where the organization already has repeatable inputs, clear owners, and measurable outcomes.",
                "bullets": [
                    "Proposal and report generation",
                    "Executive briefings and presentation conversion",
                    "Knowledge-assisted analysis and refreshes",
                ],
            },
            {
                "heading": "Responsible AI and Governance",
                "body": "Responsible adoption requires policy, evaluation, source traceability, human review, and clear ownership of decisions.",
                "bullets": [
                    "Cite external and internal evidence",
                    "Keep a run manifest for every artifact",
                    "Retain prior versions for review and recovery",
                ],
            },
            {
                "heading": "Knowledge Retrieval Foundation",
                "body": "A local vector retrieval fallback proves the contract while a Pinecone adapter can be enabled when enterprise infrastructure is available.",
                "bullets": [
                    "Normalize uploaded content into searchable profiles",
                    "Retrieve relevant enterprise context per request",
                    "Keep the retrieval provider behind one interface",
                ],
            },
            {
                "heading": "Template Fidelity",
                "body": "The generator extracts structure and style from uploaded templates and carries those signals into native editable outputs.",
                "bullets": [
                    "Preserve document margins, fonts, sizes, and heading hierarchy",
                    "Preserve PPTX slide size and theme when supplied",
                    "Validate that generated text remains editable",
                ],
            },
            {
                "heading": "Competitive Analysis",
                "body": "Differentiation comes from connecting research, enterprise context, editable outputs, and conversational iteration in one traceable workflow.",
                "bullets": [
                    "Generic assistants: broad capability, limited artifact fidelity",
                    "Point tools: strong output, limited research/RAG orchestration",
                    "This POC: modular agents with traceable artifact workflows",
                ],
            },
            {
                "heading": "Delivery Roadmap",
                "body": "The POC provides a foundation for provider hardening, richer template cloning, and production deployment decisions.",
                "bullets": [
                    "Demonstrate the end-to-end sample flow",
                    "Add provider-backed retrieval and model calls",
                    "Harden security, tenancy, observability, and deployment",
                ],
            },
            {
                "heading": "Success Measures",
                "body": "Measure whether the workflow reduces time to a reviewable artifact without sacrificing editability, provenance, or style continuity.",
                "bullets": [
                    "Time from upload to first artifact",
                    "Percentage of cited claims and validated files",
                    "Edit turnaround and version recovery",
                ],
            },
            {
                "heading": "Next Steps",
                "body": "Run the sample flow, inspect the generated files, then refine content through conversational edits.",
                "bullets": [
                    "Upload the proposal and presentation templates",
                    "Request a 12-slide research-backed output",
                    "Use chat to add, condense, compare, and refresh",
                ],
            },
        ]
        body_slide_count = max(1, slide_count - 1)
        slides = [{"title": section["heading"], "bullets": section["bullets"]} for section in sections[:body_slide_count]]
        while len(slides) < body_slide_count:
            slides.append({"title": f"Extension {len(slides) + 1}", "bullets": ["The workflow remains editable, traceable, and versioned."]})
        content = {
            "title": title,
            "subtitle": request,
            "executive_summary": "This proposal describes a research-led, retrieval-grounded path for moving Generative AI from experimentation into governed enterprise workflows.",
            "sections": sections,
            "slides": slides[:body_slide_count],
            "sources": source_dicts,
            "retrieval": retrieval,
            "content_provider": self.provider_name,
            "content_fallback_reason": "Deterministic content provider selected",
            "claim_citations": [
                {"claim": section["body"], "source_urls": [source["url"] for source in source_dicts if source.get("url")]}
                for section in sections
                if source_dicts
            ],
        }
        return ContentResult(content, self.provider_name, "Deterministic content provider selected")


class OpenAICompatibleContentProvider:
    provider_name = "openai_compatible"

    def __init__(self, api_url: str | None, api_key: str | None, model: str = "", timeout: int = 30) -> None:
        self.api_url = api_url.rstrip("/") if api_url else None
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def _endpoint(self) -> str | None:
        if not self.api_url:
            return None
        return self.api_url if self.api_url.endswith("/chat/completions") else f"{self.api_url}/chat/completions"

    def _prompt(self, request: str, profiles: list[dict[str, Any]], research: ResearchResult, retrieval: list[dict[str, Any]], slide_count: int) -> str:
        profile_summary = [
            {
                "file_name": profile.get("file_name"),
                "file_type": profile.get("file_type"),
                "style": profile.get("style", {}),
                "sections": profile.get("sections", [])[:8],
                "text": profile.get("text", "")[:1800],
            }
            for profile in profiles
        ]
        payload = {
            "request": request,
            "slide_count": slide_count,
            "profiles": profile_summary,
            "research": research.to_dict(),
            "retrieval": retrieval,
        }
        return (
            "Create a concise, evidence-grounded proposal content model. Return only valid JSON with keys "
            "title, subtitle, executive_summary, sections, slides, and claim_citations. "
            "sections must be an array of objects with heading, body, bullets. slides must be an array "
            f"of exactly {max(1, slide_count - 1)} objects with title and bullets. claim_citations must "
            "map claim text to source URLs from the supplied research sources. Do not invent URLs.\n\n"
            + json.dumps(payload, ensure_ascii=False)
        )

    def _parse_content(self, raw: Any, research: ResearchResult, retrieval: list[dict[str, Any]], slide_count: int) -> dict[str, Any]:
        if isinstance(raw, dict):
            content = raw
        else:
            text = str(raw).strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0]
            content = json.loads(text)
        if not isinstance(content, dict):
            raise ValueError("LLM response was not a JSON object")
        required = {"title", "subtitle", "executive_summary", "sections", "slides"}
        if not required.issubset(content):
            raise ValueError("LLM response omitted required content keys")
        body_slide_count = max(1, slide_count - 1)
        slides = content["slides"]
        if not isinstance(slides, list) or len(slides) != body_slide_count:
            raise ValueError("LLM response returned the wrong slide count")
        if not isinstance(content["sections"], list):
            raise ValueError("LLM sections must be an array")
        content["slides"] = [
            {"title": str(slide.get("title", "Untitled")), "bullets": [str(item) for item in slide.get("bullets", [])]}
            for slide in slides
            if isinstance(slide, dict)
        ]
        content["sources"] = _source_dicts(research)
        content["retrieval"] = retrieval
        content["content_provider"] = self.provider_name
        allowed_urls = {source.get("url") for source in content["sources"]}
        citations = []
        for item in content.get("claim_citations", []):
            if not isinstance(item, dict):
                continue
            urls = [url for url in item.get("source_urls", []) if url in allowed_urls]
            if item.get("claim") and urls:
                citations.append({"claim": str(item["claim"]), "source_urls": urls})
        content["claim_citations"] = citations
        return content

    def generate(self, request: str, profiles: list[dict[str, Any]], research: ResearchResult, retrieval: list[dict[str, Any]], slide_count: int = 12) -> ContentResult:
        endpoint = self._endpoint()
        if not endpoint:
            raise RuntimeError("LLM_API_URL is not configured")
        body = {
            "model": self.model or "default",
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": "You produce structured business proposal content grounded only in supplied context."},
                {"role": "user", "content": self._prompt(request, profiles, research, retrieval, slide_count)},
            ],
        }
        headers = {"Accept": "application/json", "Content-Type": "application/json", "User-Agent": "DocumentPPTPOC/1.0"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
            headers["X-API-Key"] = self.api_key
        request_obj = urllib.request.Request(endpoint, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
        with urllib.request.urlopen(request_obj, timeout=self.timeout) as response:
            payload = json.loads(response.read().decode("utf-8", "ignore"))
        message = payload.get("choices", [{}])[0].get("message", {}) if isinstance(payload, dict) else {}
        raw = message.get("content") if isinstance(message, dict) else None
        if raw is None:
            raise ValueError("LLM response did not contain choices[0].message.content")
        return ContentResult(self._parse_content(raw, research, retrieval, slide_count), self.provider_name)


class ResilientContentProvider:
    def __init__(self, primary: Any, fallback: DeterministicContentProvider) -> None:
        self.primary = primary
        self.fallback = fallback

    def generate(self, request: str, profiles: list[dict[str, Any]], research: ResearchResult, retrieval: list[dict[str, Any]], slide_count: int = 12) -> ContentResult:
        try:
            return self.primary.generate(request, profiles, research, retrieval, slide_count)
        except Exception as exc:
            result = self.fallback.generate(request, profiles, research, retrieval, slide_count)
            reason = f"{self.primary.provider_name} failed: {type(exc).__name__}"
            result.fallback_reason = reason
            result.content["content_fallback_reason"] = reason
            return result


def build_content_provider(settings: Any) -> Any:
    if settings.llm_provider == "openai_compatible":
        return ResilientContentProvider(
            OpenAICompatibleContentProvider(settings.llm_api_url, settings.llm_api_key, settings.llm_model),
            DeterministicContentProvider(),
        )
    return DeterministicContentProvider()

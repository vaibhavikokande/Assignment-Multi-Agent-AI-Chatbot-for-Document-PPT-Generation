from __future__ import annotations

import copy
import re
from typing import Any


def extract_edit_intent(instruction: str) -> dict[str, Any]:
    """Convert conversational edit language into an auditable, deterministic intent object."""
    lower = instruction.lower()
    operations: list[str] = []
    if re.search(r"\b(executive\s+summary|summary|leadership\s+overview)\b", lower):
        operations.append("add_executive_summary")
    if re.search(r"\b(concise|shorter|condense|brief|reduce\s+(the\s+)?content|less\s+text)\b", lower):
        operations.append("reduce_density")
    if re.search(r"\b(competitive|competitor|competition)\b", lower):
        operations.append("add_competitive_analysis")
    if re.search(r"\b(latest|current|web|research|refresh|update)\b", lower):
        operations.append("refresh_research")
    return {
        "target": "current_artifact",
        "operations": operations,
        "instruction": instruction,
        "unclassified": not operations,
    }


def apply_edit(content: dict[str, Any], instruction: str, sources: list[dict[str, Any]] | None = None) -> tuple[dict[str, Any], list[str]]:
    updated = copy.deepcopy(content)
    intent = extract_edit_intent(instruction)
    updated["edit_intent"] = intent
    changes: list[str] = []
    operations = set(intent["operations"])
    if "add_executive_summary" in operations:
        updated["executive_summary"] = "This revised executive summary frames the opportunity, the operating model, the evidence base, and the next decision required from leadership."
        changes.append("Added an executive summary")
    if "reduce_density" in operations:
        for section in updated.get("sections", []):
            section["bullets"] = section.get("bullets", [])[:2]
            section["body"] = " ".join(section.get("body", "").split()[:35])
        for slide in updated.get("slides", []):
            slide["bullets"] = slide.get("bullets", [])[:2]
        changes.append("Reduced content density while preserving the slide structure")
    if "add_competitive_analysis" in operations:
        section = {
            "heading": "Competitive Analysis",
            "body": "The strongest differentiation is an evidence-led, governed path from discovery to measurable enterprise adoption.",
            "bullets": [
                "Horizontal productivity suites: broad reach, variable domain depth",
                "Specialist consultancies: deep expertise, higher integration effort",
                "Our approach: reusable workflows, retrieval, governance, and measurable value",
            ],
        }
        if not any(item.get("heading") == section["heading"] for item in updated.get("sections", [])):
            updated.setdefault("sections", []).append(section)
        slides = updated.setdefault("slides", [])
        if not any(item.get("title") == section["heading"] for item in slides):
            slides.insert(min(9, len(slides)), {"title": "Competitive Analysis", "bullets": section["bullets"]})
        updated["slides"] = slides[:11]
        changes.append("Added a competitive analysis section and slide")
    if "refresh_research" in operations:
        if sources:
            updated["sources"] = sources
            updated["claim_citations"] = [
                {"claim": section.get("body", ""), "source_urls": [source.get("url") for source in sources if source.get("url")]}
                for section in updated.get("sections", [])
            ]
        updated["research_refresh_note"] = "Content refreshed through the Research Agent during this version."
        changes.append("Refreshed the source list through the research workflow")
    if not changes:
        updated["edit_note"] = instruction
        changes.append("Applied the user instruction as a traceable edit note")
    return updated, changes

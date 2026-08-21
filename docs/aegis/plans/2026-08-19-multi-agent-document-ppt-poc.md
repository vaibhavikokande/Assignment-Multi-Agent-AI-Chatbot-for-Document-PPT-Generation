# Multi-Agent Document and PPT Generation POC

## Goal

Build a runnable POC for the assignment’s end-to-end scenario: upload document and presentation templates, request current research and a 12-slide output, receive editable DOCX/PPTX artifacts with citations, then modify them through natural-language chat while preserving style and version history.

## Architecture

```text
Browser UI -> HTTP API -> SupervisorAgent
                         -> TemplateAnalysisAgent -> parsers
                         -> ResearchAgent -> live web/fallback provider
                         -> RetrievalAgent -> local TF-IDF/Pinecone seam
                         -> ContentAgent -> deterministic demo content
                         -> DocumentAgent / PresentationAgent -> native Open XML
                         -> ValidationAgent -> artifact checks
                         -> EditingAgent -> versioned regeneration
                         -> ArtifactRepository -> local storage
```

The supervisor owns sequencing and trace assembly. Agents return typed results. The repository owns artifact IDs, versions, source metadata, and run manifests.

## Tech stack

- Python 3.10+ and standard-library HTTP server.
- `python-docx` for editable DOCX.
- `python-pptx` for editable PPTX and template round-tripping.
- `pypdf` for PDF extraction.
- Pillow with optional Tesseract OCR.
- Standard-library TF-IDF retrieval, with a Pinecone-compatible adapter seam.
- Standard-library URL fetching for DuckDuckGo HTML research.
- Vanilla HTML/CSS/JavaScript frontend.

## Baseline / authority refs

- `docs/aegis/baseline/2026-08-19-initial-baseline.md`.
- The attached assignment PDF and active task objective.
- LangGraph supervisor pattern and official `python-docx`/`python-pptx` documentation.

## Compatibility boundary

- Keep DOCX/PPTX native and editable.
- Preserve PPTX size/theme by using the uploaded deck as the presentation base.
- Preserve document fonts, sizes, colors, margins, and heading profile.
- Do not make external credentials mandatory.
- Keep prior artifact versions downloadable.

## TDD Route

- Mode: off.
- Decision: skipped; the user did not request strict test-first development.
- Test posture: focused post-change regression plus an executable end-to-end demo.
- Verification: `python -m unittest discover -s tests -v`, demo run, and native artifact inspection.

## Requirement ready check

- Source: attached assignment PDF inspected across all pages.
- Scenario: upload → research/RAG → generation → edit.
- Acceptance: editable outputs, style preservation, citations, traceability, versioning, documentation, samples, and GitHub-ready packaging.
- Open decision-changing questions: none; provider/framework choices are implementation-owned.
- Decision: ready.

## Change necessity

- User-visible need: a working system, not prose only.
- No-code option: cannot satisfy upload, generation, editing, and artifact verification.
- Minimum boundary: one modular local application with typed contracts, API, UI, agents, parsers, generators, repository, samples, and tests.
- Decision: code-change.

## Architecture integrity and existence checks

The repository has no owners to reuse, so new owners are justified. The supervisor is the single workflow owner; the repository is the single version owner; provider adapters are thin external seams with local fallbacks. No duplicate orchestration or persistence path is planned.

## Plan-time complexity check

The main risk is a monolithic `main.py`. Keep models, repository, file services, agents, generators, API composition, and static UI in separate owners. No legacy path or retirement track exists.

## Execution readiness view

- Intent lock: full local POC with the 12-slide proposal scenario.
- Scope fence: browser/API, optional providers, editable artifacts, samples, docs, tests; exclude production operations.
- Baseline lock: empty workspace.
- Approved behavior: upload, analysis, research, retrieval, generation, validation, editing, conversion, citations, trace, versions, downloads.
- Compatibility: native Open XML, style profile, offline demo, append-only versions.
- Test obligations: parser/retrieval/version tests, API smoke flow, native artifact checks, demo run.
- Drift rule: return here if credentials become mandatory or the main acceptance flow is weakened.

## Tasks

### 1. Backend substrate

Files: `app/models.py`, `app/repository.py`, `app/config.py`, `storage/.gitkeep`.

Create typed contracts and a JSON-backed local registry for uploads, runs, artifacts, and versions. Verify imports and a temporary repository round trip.

### 2. Ingestion and template analysis

Files: `app/parsers.py`, `samples/create_samples.py`, `tests/test_parsers.py`.

Support DOCX, PDF, PPT/PPTX, and images; attempt legacy `.ppt` conversion; expose OCR status; return normalized structure/style profiles. Verify sample parsing and style metrics.

### 3. Specialized agents

Files: `app/agents.py`, `app/research.py`, `app/rag.py`, `tests/test_agents.py`.

Implement supervisor, template analysis, research, retrieval, content, generation, validation, editing, and conversion agents. Verify named trace steps, sources, and enterprise retrieval.

### 4. Artifact generation and editing

Files: `app/generators.py`, `app/validation.py`, `tests/test_artifacts.py`.

Generate native DOCX/PPTX, preserve profiles, embed citations, validate outputs, edit content, convert formats, and append versions. Verify editable text, 12 slides, version 2, and prior-version retention.

### 5. API and browser UI

Files: `app/main.py`, `app/static/index.html`, `app/static/app.js`, `app/static/styles.css`, `tests/test_api.py`.

Expose health, upload, chat, run, artifact, version, conversion, and download routes. Build a static chatbot UI. Verify the main flow through HTTP.

### 6. Packaging and completion evidence

Files: `README.md`, `requirements.txt`, `samples/`, `scripts/run_demo.py`, `tests/`.

Document setup/usage, dependencies, optional providers, sample inputs/outputs, and verification. Run a fresh test/demo/artifact checklist.

## Risks and mitigations

- Network search can fail: use clearly labeled demo sources.
- OCR can be absent: retain image metadata and report OCR status.
- Legacy `.ppt` conversion depends on LibreOffice.
- No LLM key: deterministic content planner keeps the demo runnable.
- Style fidelity: preserve profile and validate native structure rather than claiming pixel identity.

## Requirement evidence matrix

| Requirement | Evidence |
| --- | --- |
| Formats and template analysis | parser tests and upload response |
| Multi-agent orchestration | named agent trace |
| Web research and RAG | provider result/fallback plus retrieval hits |
| Editable outputs | native DOCX/PPTX parse checks |
| Style and editing | profile metadata and versioned edit test |
| Conversion | conversion endpoint and artifact check |
| Citations/traceability | source list and run manifest |
| Validation/versioning | validation report and version list |
| Deliverables | README, requirements, samples, tests, demo script |

## Retirement

There is no old implementation to retire. Optional provider adapters remain thin and must not become parallel owners of orchestration or persistence.

## Compliance repair extension

The post-implementation audit found that the original POC proved only the local happy path. The repair extension keeps the native Open XML and local-fallback compatibility boundaries while making fallback selection explicit and adding evidence for the PDF's negative paths.

- Harden upload staging, file signatures, browser-session auth, CORS, and HTTP error semantics.
- Add configurable web, LLM, OCR, and enterprise retrieval provider contracts with deterministic offline tests.
- Preserve richer template structure and current-artifact lineage through generation, editing, and conversion.
- Add API, OCR, provider, artifact, visual, UI, and CI compliance checks.

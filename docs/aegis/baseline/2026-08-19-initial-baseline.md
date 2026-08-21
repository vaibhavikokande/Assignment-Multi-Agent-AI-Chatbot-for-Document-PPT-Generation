# Multi-Agent Document and PPT POC Initial Baseline

Date: `2026-08-19`
Status: `initial dual-baseline snapshot`

## Product / requirement baseline

The system must support DOCX, PDF, PPT/PPTX, images, scanned content, template analysis, real-time research, enterprise RAG, multi-agent orchestration, editable DOCX/PPTX generation, style preservation, natural-language editing, bidirectional conversion, citations, traceability, validation, versioning, secure modular APIs, documentation, samples, and GitHub deployment.

Non-negotiables:

1. Supervisor and specialized-agent responsibilities are visible in the runtime trace.
2. The demo creates a proposal and a 12-slide presentation from uploaded templates.
3. Outputs are editable DOCX/PPTX files, not screenshots.
4. Conversational edits create a new version while retaining the prior artifact.
5. The project includes README setup/usage guidance and `requirements.txt`.

Product non-goals are production-scale authentication, billing, multi-tenant isolation, SLAs, paid-provider provisioning, and a specific LLM, frontend framework, host, or vector database.

## Architecture / runtime boundary baseline

The workspace contains no existing code, API, package manifest, README, or tests. Use explicit owners for API routing, domain models, file services, agent orchestration, retrieval, research, generation, and persistence.

Canonical ownership:

- `app/main.py`: HTTP and static UI composition.
- `app/models.py`: normalized request, profile, trace, and artifact contracts.
- `app/parsers.py` and `app/generators.py`: file transformation boundaries.
- `app/agents.py`: supervisor and specialized agent execution.
- `app/repository.py`: persistent metadata and artifact versions.
- `app/static/`: browser interaction.

Provider adapters may fall back locally. There is no legacy path to retire.

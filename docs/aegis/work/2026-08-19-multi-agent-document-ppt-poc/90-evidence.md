# Evidence Bundle Draft

Date: `2026-08-19`

## Commands and results

- `python -m compileall -q app samples scripts tests` — passed.
- `python -m unittest discover -s tests -v` — 14 tests passed, including API, OCR/image/PDF, legacy PPT, provider, RAG, UI, lineage, and core contract coverage.
- `python scripts/run_demo.py` — fresh run `run_d0d9b67da1f8` completed with two validated artifacts.
- HTTP `GET /api/health` — returned `status: ok`.
- HTTP multipart `POST /api/upload` for DOCX and PPTX — returned profiles with text/style/slide metrics.
- HTTP `POST /api/chat` — returned `completed`, a named multi-agent trace, editable DOCX, and a 12-slide PPTX.
- HTTP conversational `POST /api/chat` with `artifact_id` — returned version 2; artifact endpoint reported two retained versions.
- HTTP `POST /api/convert` — returned a validated PPTX from a DOCX artifact.
- `render_docx.py` — final DOCX rendered to 3 pages; all pages visually inspected.
- `render_slides.py` — final PPTX rendered to 12 slides; all slides visually inspected.
- `slides_test.py` — `Test passed. No overflow detected.`
- Native inspection — generated DOCX has editable paragraphs; generated PPTX has 12 slides, editable text shapes, and `[Sources]` notes on all 12 slides.
- Packaging inspection — `samples/generated/Generative_AI_Trends_Proposal.docx` and `samples/generated/Generative_AI_Trends_Presentation.pptx` exist; the latter has 12 slides and source notes on all slides.
- Pre-publication integrity — staged diff check passed; credential-pattern scan found no credential-like values.
- GitHub publication — `gh repo view` confirmed public `main` repository `https://github.com/mayur200904/multi-agent-document-ppt-poc`; remote API confirmed the README, requirements, app entrypoint, generated DOCX/PPTX samples, and tests; implementation commit `004aaf5da9d12d2f091a7e6f01c888c3ce888da9` and evidence commit `3578aeb` are present on the remote branch.
- Compliance repair publication — `git push origin main` succeeded; remote `refs/heads/main` resolves to `d43e0dc1a2df2c33c93657fe7fa6f10774afa370`; `gh repo view` confirms the repository remains public at `https://github.com/mayur200904/multi-agent-document-ppt-poc`.
- Compliance audit — isolated API/UI execution reproduced the gaps listed in the repair plan: live DuckDuckGo fell back to the deterministic provider, image-only PDF OCR was unavailable before the CLI fallback, the Pinecone adapter returned no results, template output was structurally but not deeply style-preserving, and invalid `.txt` uploads were persisted before this repair.
- Slice 1 verification — `python -m compileall -q app samples scripts tests` passed; `python -m unittest discover -s tests -v` passed all 5 existing tests after staged upload validation, signature checks, OCR CLI fallback, same-origin browser sessions, origin-scoped CORS, and 404 handling were added.
- Compliance repair verification — JSON web-provider and OpenAI-compatible LLM responses were mocked and parsed; misconfigured LLM routing fell back explicitly; Pinecone-compatible upsert/query paths returned mocked remote hits; `samples/input/enterprise_context.md` was ingested and retrieved; and live-default research recorded the DuckDuckGo anti-bot fallback reason.
- OCR/format verification — Tesseract CLI OCR returned text for a generated image and image-only PDF; LibreOffice converted a generated legacy `.ppt` and the parser profiled it as `converted_to_pptx`.
- Fidelity verification — generated DOCX assertions passed margins, shared fonts, and headers/footers; generated PPTX assertions passed slide size, layouts, and 100% sampled source geometry preservation.
- API E2E verification — API-key unauthorized access returned 401; browser session access succeeded without exposing the API key; rejected `.txt` upload returned 400 without increasing persisted upload count; generation, downloads, prior-version retrieval, editing, conversion, conversion RunRecord retrieval, unknown-artifact 404, and hostile-origin CORS checks passed.
- Browser smoke verification — Chrome loaded the API-key-enabled UI, observed the HttpOnly `poc_session`, uploaded both templates, completed generation, rendered the Supervisor trace, and created a versioned edit.
- Visual verification — bundled `render_docx.py` rendered 5 DOCX pages; bundled `render_slides.py` rendered 12 PPTX slides; bundled `slides_test.py` reported `Test passed. No overflow detected.`
- CI verification — `.github/workflows/ci.yml` runs compile, the complete test suite, and the deterministic demo with OCR dependencies installed.

## Covered requirements

Upload formats, template profiling, specialized-agent trace, web research adapter, local enterprise retrieval, editable generation, citations, traceability, validation, versioning, conversational edits, bidirectional conversion, API, UI, README, requirements, and samples are covered by code and runtime evidence.

## Uncovered requirement

The assignment’s GitHub source-publication requirement is covered. Production hardening remains outside this POC’s acceptance boundary: live provider credentials are optional, while the local retrieval and deterministic content paths are verified.

Remaining operational boundary: live provider credentials and hosted production deployment are intentionally optional for this credential-optional POC; the configured provider contracts and explicit deterministic fallbacks are covered locally and by mocked contract tests.

## Confidence

Core local POC: `A` — direct runtime, native artifact, API, browser, OCR, provider-contract, lineage, and visual evidence.
GitHub publication: `A` — public repository, branch, commit, and required remote files directly verified.

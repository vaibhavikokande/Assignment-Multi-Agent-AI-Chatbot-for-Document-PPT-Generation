# Artifact Studio: Multi-Agent Document & PPT Generation POC

Artifact Studio is a local, runnable proof of concept for the assignment: a supervisor-led multi-agent chatbot that analyzes uploaded templates, researches a request, retrieves enterprise context, generates editable DOCX/PPTX outputs, validates them, and supports conversational versioned editing.

Repository: [https://github.com/vaibhavikokande/Assignment-Multi-Agent-AI-Chatbot-for-Document-PPT-Generation.git](https://github.com/vaibhavikokande/Assignment-Multi-Agent-AI-Chatbot-for-Document-PPT-Generation.git)

## What is implemented

- Upload support for DOCX, PDF, PPT/PPTX, and image formats.
- DOCX/PPTX structure, text, layout, font, margin, geometry, styles, headers/footers, tables, masters, layouts, backgrounds, shapes, and slide-size profiling.
- OCR for images and scanned PDFs through `pytesseract` or the direct Tesseract CLI fallback, with status and extracted text retained in profiles and traces.
- Supervisor trace with specialized template-analysis, research, retrieval, content, validation, editing, and conversion responsibilities.
- Configurable live JSON/API web research and DuckDuckGo research adapters with clearly labeled deterministic fallback sources.
- Local TF-IDF enterprise retrieval that requires no account, configurable enterprise-file ingestion, plus a functional Pinecone-compatible data-plane adapter.
- Credential-optional structured LLM content provider with deterministic fallback and provider metadata.
- Native editable DOCX and PPTX generation; uploaded DOCX/PPTX structures are reused as the generation base when supplied.
- A shared visual design system applies a template-derived colour palette, type scale, cover panel, callouts,
  numbered rule-underlined headings, and styled evidence tables to the DOCX, and a slide rail, section labels,
  accent rules, coloured bullets, and page-numbered footers to the PPTX.
- Structured conversational edit intents for executive summaries, concise presentations, competitive analysis, and research refreshes.
- Append-only artifact versions, claim-level citations, source lineage, conversion run manifests, and downloads.
- Staged upload validation, signature checks, origin-scoped CORS, and HttpOnly browser-session authentication when `API_KEY` is configured.
- Document-to-presentation and presentation-to-document conversion endpoint.
- Browser UI with upload, supervisor request, trace, sources, artifact downloads, and versioned editing.

## Setup

Python 3.10+ is required, including Python 3.13. The `cgi` module used for multipart uploads was removed from the
standard library in 3.13, so `requirements.txt` pulls in the `legacy-cgi` backport automatically on that version.
The POC runs with the dependencies listed in `requirements.txt`:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

For OCR and legacy PowerPoint conversion, install the system dependencies. On macOS, for example:

```bash
brew install tesseract poppler libreoffice
```

If Tesseract is unavailable, image and scanned-PDF profiles retain an explicit OCR-unavailable status. Legacy `.ppt` conversion requires LibreOffice/`soffice`.

## Run the application

```bash
python -m app.main
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). The default app is credential-free and stores runtime state under `storage/`.

## Run the assignment demo

```bash
python samples/create_samples.py
python scripts/run_demo.py
```

The demo creates `samples/input/Company_Proposal.docx` and `samples/input/Company_Template.pptx`, runs the exact proposal plus 12-slide workflow, and prints the run ID, artifact metadata, and agent trace. Generated runtime files are stored under `storage/`.

The latest validated sample outputs are also checked into `samples/generated/Generative_AI_Trends_Proposal.docx` and `samples/generated/Generative_AI_Trends_Presentation.pptx`.

## API surface

- `GET /api/health`
- `GET /api/uploads`
- `POST /api/upload` with multipart field `file`
- `POST /api/chat` with `{message, upload_ids, artifact_id?, slide_count?}`
- `GET /api/runs/{run_id}`
- `GET /api/artifacts`
- `GET /api/artifacts/{artifact_id}`
- `GET /api/artifacts/{artifact_id}/download?version=1`
- `POST /api/convert` with `{artifact_id, target_format: "docx"|"pptx"}`

## Provider configuration

Copy `.env.example` to `.env` for local testing. The application loads `.env` automatically at startup, while variables already present in your shell take priority. `.env` is ignored by Git; keep real keys only there or in a deployment secret manager.

- `APP_STORAGE_DIR`: alternate local storage directory.
- `WEB_SEARCH_ENABLED=false`: explicitly select offline research; the run metadata records the fallback reason.
- `WEB_SEARCH_PROVIDER`: `duckduckgo_html` (default), `json_api`, or `tavily`.
- `WEB_SEARCH_API_URL` and `WEB_SEARCH_API_KEY`: optional JSON search endpoint and credential.
- `TAVILY_API_KEY`: credential for `WEB_SEARCH_PROVIDER=tavily`; the app sends it only as a bearer-authenticated request to Tavily's search endpoint.
- `LLM_PROVIDER`: `deterministic` (default) or `openai_compatible`.
- `LLM_API_URL`, `LLM_API_KEY`, and `LLM_MODEL`: optional structured JSON content provider configuration.
- `ENTERPRISE_KB_DIR`: directory containing `.md`/`.txt` enterprise knowledge files; defaults to `samples/input`.
- `PINECONE_API_KEY`, `PINECONE_INDEX_HOST`, and `PINECONE_NAMESPACE`: optional Pinecone-compatible retrieval configuration. The namespace defaults to Pinecone's `__default__` namespace.
- `PINECONE_API_VERSION`: Pinecone data-plane version header; defaults to the currently supported `2026-04` version.
- `PINECONE_MODE`: `vectors` (default, a custom 128-dimension external-vector index) or `integrated` (a Pinecone index with hosted embeddings such as `llama-text-embed-v2`).
- `PINECONE_TEXT_FIELD`: field-map target for `PINECONE_MODE=integrated`; it must exactly match the index's configured field map (for example, `text` or `chunk_text`).
- `OCR_ENABLED=false`: disable OCR explicitly.
- `ALLOWED_ORIGINS`: comma-separated browser/API origins; defaults to local app origins.
- `MAX_UPLOAD_BYTES`: upload limit, default 25 MB.
- `APP_HOST` and `APP_PORT`: local server binding.
- `API_KEY`: optional shared key for API routes; send it as `X-API-Key`. Health remains public for liveness checks.

The POC intentionally keeps provider credentials optional. When `API_KEY` is configured, loading the browser UI issues an HttpOnly session cookie so the JavaScript client does not need to expose the key. A production implementation would still add tenant isolation, encrypted storage, provider-backed embeddings, model routing, queueing, and deployment controls.

To run the assignment workflow with real-time Tavily research, set the key in your shell or deployment secret manager (never commit it), then run the demo:

```bash
export WEB_SEARCH_PROVIDER=tavily
export TAVILY_API_KEY='tvly-your-key'
python scripts/run_demo.py
```

The saved run metadata reports `research_provider: tavily_live` when the request succeeds. If Tavily is unavailable or the key is missing, the run records an explicit fallback reason instead.

For a Pinecone integrated-embedding index, configure the index host, namespace, and its field-map target in your shell or deployment secret manager. The app sends text records to Pinecone for embedding and uses a text search rather than sending its local 128-dimension vectors:

```bash
export PINECONE_MODE=integrated
export PINECONE_NAMESPACE=__default__
export PINECONE_TEXT_FIELD=text  # replace with the target configured in the Pinecone field map
export PINECONE_API_KEY='your-rotated-key'
export PINECONE_INDEX_HOST='https://your-index-host'
python scripts/run_demo.py
```

Never put provider credentials in `.env` files committed to Git or in source code.

## Project map

- `app/agents.py`: supervisor and specialized agent workflow.
- `app/parsers.py`: document, PDF, slide, image, and legacy PPT analysis.
- `app/generators.py`: native editable DOCX/PPTX generation and conversion content.
- `app/design.py`: shared palette, type scale, and schema-ordered OOXML styling helpers.
- `app/research.py`: live research adapter and fallback sources.
- `app/rag.py`: enterprise knowledge retrieval and provider seam.
- `app/repository.py`: upload, run, artifact, and version source of truth.
- `app/main.py`: API server and static web delivery.
- `samples/`: assignment sample templates and generated outputs.
- `tests/`: executable contract and API/OCR/provider/UI compliance tests.

## Verification

```bash
python -m unittest discover -s tests -v
python scripts/run_demo.py
```

The tests verify template parsing, local and enterprise-file retrieval, mocked live-provider routing, Pinecone request routing, OCR for images/scanned PDFs, editable native output, the named multi-agent trace, 12-slide generation, validation, versioned editing, API authentication and error statuses, conversion run lineage, invalid-upload rejection, and browser UI contracts. GitHub Actions runs compile, the complete test suite, and the deterministic demo.

## Internet research references

The architecture follows the supervisor pattern documented by [LangGraph](https://reference.langchain.com/python/langgraph-supervisor). Comparable projects such as [GenSlide](https://github.com/mehdimo/GenSlide) use an agentic parse/orchestrate/generate/review pipeline for PPTX output. Native editability is supported by [python-pptx](https://python-pptx.readthedocs.io/en/stable/) and the `python-docx` package; provider and rendering limitations are documented in the code’s local fallback boundaries.

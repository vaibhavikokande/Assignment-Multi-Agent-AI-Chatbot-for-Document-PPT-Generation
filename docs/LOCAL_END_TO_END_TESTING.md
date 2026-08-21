# Local End-to-End Testing Guide

This guide lets you run the complete Artifact Studio workflow with live Tavily research, Pinecone retrieval, and an OpenRouter-compatible model. Provider keys must be newly generated and kept only in your local `.env` file.

## 1. Prepare the project

```bash
cd "/Users/mayursantoshtarate/Desktop/project/untitled folder 7"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

The application reads `.env` automatically when it starts. The file is ignored by Git.

## 2. Fill in `.env`

Use the following values as the complete configuration shape. Replace only the values marked `REPLACE_ME`; do not copy old keys exposed in chat.

```env
APP_HOST=127.0.0.1
APP_PORT=8000
APP_STORAGE_DIR=storage
DEMO_MODE=true
OCR_ENABLED=true
MAX_UPLOAD_BYTES=26214400
ALLOWED_ORIGINS=http://127.0.0.1:8000,http://localhost:8000
API_KEY=

WEB_SEARCH_ENABLED=true
WEB_SEARCH_PROVIDER=tavily
TAVILY_API_KEY=REPLACE_ME

LLM_PROVIDER=openai_compatible
LLM_API_URL=https://openrouter.ai/api/v1
LLM_API_KEY=REPLACE_ME
LLM_MODEL=REPLACE_WITH_AN_EXACT_OPENROUTER_MODEL_SLUG

ENTERPRISE_KB_DIR=samples/input
PINECONE_MODE=integrated
PINECONE_API_KEY=REPLACE_ME
PINECONE_INDEX_HOST=REPLACE_WITH_YOUR_PINECONE_INDEX_HOST
PINECONE_NAMESPACE=__default__
PINECONE_API_VERSION=2026-04
PINECONE_TEXT_FIELD=REPLACE_WITH_YOUR_INDEX_FIELD_MAP_TARGET
```

For the Pinecone index, open **Configuration** and read the embed `field_map`. Set `PINECONE_TEXT_FIELD` to its target field name, such as `text` or `chunk_text`. It is not visible in the supplied screenshot, so do not guess.

## 3. Choose the provided upload template

Use the included `samples/input/Northstar_Retail_AI_Enablement_Proposal_Template.docx`. It is an editable two-page retail proposal with title, header/footer, headings, lists, and a 90-day roadmap table.

If you delete it and need to recreate it:

```bash
python -c "from samples.create_samples import create_retail_ai_upload_template; print(create_retail_ai_upload_template())"
```

## 4. Start the application

```bash
python -m app.main
```

Open `http://127.0.0.1:8000`.

## 5. Run the browser workflow

1. In **Template Input**, select `Northstar_Retail_AI_Enablement_Proposal_Template.docx`.
2. Wait for the upload profile to complete.
3. Paste the following supervisor request.
4. Select **Run supervisor workflow**.
5. Review the agent trace, citations, and the downloadable DOCX/PPTX artifacts.

## Supervisor request

```text
Using the uploaded Northstar Retail AI Enablement Proposal template, research current retail AI trends with an emphasis on customer service, store operations, and inventory planning. Create a board-ready proposal and a 12-slide PowerPoint that preserve the template's concise executive tone, navy-and-blue hierarchy, structured 90-day roadmap, and measurable-outcome framing. Cite all current research and clearly distinguish external findings from the supplied template context.
```

## 6. Verify the live providers

In the generated run trace or artifact lineage, confirm:

- `research_provider` is `tavily_live`.
- `retrieval_provider` is `pinecone_integrated` after Pinecone has indexed the records. Pinecone indexing can take a short time, so rerun once if the first request records local fallback.
- `content_provider` is `openai_compatible`.

Then create a versioned edit by selecting the DOCX artifact and submitting:

```text
Add a one-paragraph executive summary with three measurable pilot outcomes, while preserving the existing document style.
```

## Troubleshooting

- `deterministic_demo_fallback`: Tavily is disabled, its key is missing, or its request failed. Check `WEB_SEARCH_ENABLED`, `WEB_SEARCH_PROVIDER`, and `TAVILY_API_KEY`.
- `local` retrieval: Pinecone is missing a setting, the field map is wrong, or the new records are not searchable yet. Recheck `PINECONE_INDEX_HOST`, `PINECONE_TEXT_FIELD`, and wait briefly.
- `deterministic_fallback`: the OpenRouter endpoint, key, or model slug is invalid, or the model response was not valid structured content.
- Port in use: change `APP_PORT` in `.env`, restart the server, and open the matching local URL.

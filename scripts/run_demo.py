from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.agents import SupervisorAgent
from app.config import get_settings
from app.repository import ArtifactRepository
from samples.create_samples import create_samples


def main() -> int:
    sample_paths = [ROOT / "samples/input/Company_Proposal.docx", ROOT / "samples/input/Company_Template.pptx"]
    if not all(path.exists() for path in sample_paths):
        create_samples()
    settings = get_settings()
    repository = ArtifactRepository(settings)
    uploads = []
    for path in sample_paths:
        record = repository.save_upload(path.name, path.read_bytes())
        uploads.append(record["upload_id"])
    supervisor = SupervisorAgent(repository, web_search_enabled=settings.web_search_enabled)
    run = supervisor.run("Research the latest Generative AI trends and create a proposal and 12-slide presentation using the same tone and style as the uploaded files.", uploads, slide_count=12)
    print(json.dumps({"run_id": run.get("run_id"), "status": run.get("status"), "artifacts": run.get("artifacts"), "step_agents": [step.get("agent") for step in run.get("steps", [])]}, indent=2))
    if run.get("status") != "completed" or len(run.get("artifacts", [])) != 2:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.agents import SupervisorAgent
from app.config import Settings
from app.generators import generate_docx, generate_pptx
from app.parsers import parse_file
from app.rag import EnterpriseKnowledgeBase
from app.repository import ArtifactRepository
from samples.create_samples import create_retail_ai_upload_template, create_sample_docx, create_sample_pptx


class POCContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.settings = Settings(root_dir=root, storage_dir=root / "storage", web_search_enabled=False)
        self.repository = ArtifactRepository(self.settings)
        self.doc_template = create_sample_docx(root / "Company_Proposal.docx")
        self.ppt_template = create_sample_pptx(root / "Company_Template.pptx")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_parsers_extract_template_profiles(self) -> None:
        doc = parse_file(self.doc_template)
        ppt = parse_file(self.ppt_template)
        self.assertGreater(doc.paragraph_count, 0)
        self.assertGreater(ppt.slide_count, 0)
        self.assertIn("font_names", doc.style)
        self.assertIn("slide_size", ppt.style)

    def test_retail_upload_template_is_profiled(self) -> None:
        template = create_retail_ai_upload_template(Path(self.temp.name) / "Retail_AI_Template.docx")
        profile = parse_file(template)
        self.assertEqual(profile.file_type, "docx")
        self.assertEqual(profile.table_count, 2)
        self.assertIn("Northstar Retail", profile.text)
        self.assertIn("Calibri", profile.style["font_names"])

    def test_local_rag_returns_enterprise_context(self) -> None:
        knowledge = EnterpriseKnowledgeBase()
        hits = knowledge.retrieve("secure enterprise workflow adoption")
        self.assertTrue(hits)
        self.assertEqual(hits[0]["source_type"], "enterprise")

    def test_native_generators_create_editable_files(self) -> None:
        content = {"title": "Test", "executive_summary": "Summary", "sections": [{"heading": "One", "body": "Body", "bullets": ["Bullet"]}], "slides": [{"title": str(i), "bullets": ["Bullet"]} for i in range(11)], "sources": []}
        doc_out = Path(self.temp.name) / "out.docx"
        ppt_out = Path(self.temp.name) / "out.pptx"
        generate_docx(content, parse_file(self.doc_template).to_dict(), doc_out)
        generate_pptx(content, parse_file(self.ppt_template).to_dict(), ppt_out, self.ppt_template)
        self.assertGreater(doc_out.stat().st_size, 1000)
        self.assertGreater(ppt_out.stat().st_size, 1000)
        self.assertEqual(parse_file(ppt_out).slide_count, 12)

    def test_supervisor_generates_two_artifacts_and_trace(self) -> None:
        uploads = [self.repository.save_upload(path.name, path.read_bytes())["upload_id"] for path in (self.doc_template, self.ppt_template)]
        supervisor = SupervisorAgent(self.repository, web_search_enabled=False)
        run = supervisor.run("Create a research-backed proposal and 12-slide presentation", uploads, slide_count=12)
        self.assertEqual(run["status"], "completed")
        self.assertEqual(len(run["artifacts"]), 2)
        agents = {step["agent"] for step in run["steps"]}
        self.assertTrue({"SupervisorAgent", "TemplateAnalysisAgent", "ResearchAgent", "RetrievalAgent", "ContentAgent", "DocumentGenerationAgent", "PPTGenerationAgent", "ValidationAgent"}.issubset(agents))
        self.assertTrue(all(artifact["validation"]["passed"] for artifact in run["artifacts"]))

    def test_conversational_edit_increments_version(self) -> None:
        uploads = [self.repository.save_upload(path.name, path.read_bytes())["upload_id"] for path in (self.doc_template, self.ppt_template)]
        supervisor = SupervisorAgent(self.repository, web_search_enabled=False)
        run = supervisor.run("Create a proposal and presentation", uploads)
        artifact_id = next(item["artifact_id"] for item in run["artifacts"] if item["file_type"] == "docx")
        edited = supervisor.run("Add an executive summary and competitive analysis section.", edit_artifact_id=artifact_id)
        self.assertEqual(edited["status"], "completed")
        self.assertEqual(self.repository.get_artifact(artifact_id)["current_version"], 2)
        self.assertEqual(len(self.repository.get_artifact(artifact_id)["versions"]), 2)


if __name__ == "__main__":
    unittest.main()

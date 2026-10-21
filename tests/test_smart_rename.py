from __future__ import annotations

import base64
from pathlib import Path
import plistlib
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import zipfile

import smart_rename as rwo


def _create_minimal_text_pdf(path: Path, text: str) -> None:
    """Create a valid single-page PDF containing selectable text."""
    stream = f"BT /F1 14 Tf 50 700 Td ({text}) Tj ET".encode("ascii")
    objs = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        (
            b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n"
        ),
        f"4 0 obj\n<< /Length {len(stream)} >>\nstream\n".encode("ascii") + stream + b"\nendstream\nendobj\n",
        b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for obj in objs:
        offsets.append(len(out))
        out.extend(obj)
    xref_pos = len(out)
    out.extend(f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode("ascii"))
    for off in offsets:
        out.extend(f"{off:010d} 00000 n \n".encode("ascii"))
    out.extend(
        f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode("ascii")
    )
    _ = path.write_bytes(bytes(out))


def _create_minimal_blank_pdf(path: Path) -> None:
    """Create a valid single-page PDF with no text (simulating a scanned/image-only PDF)."""
    _create_minimal_text_pdf(path, "")


class TestRenameWithOllama(unittest.TestCase):
    temp_dir: tempfile.TemporaryDirectory[str]
    root: Path

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_vocabulary_counts_and_definitions_in_prompt(self) -> None:
        self.assertEqual(len(rwo.CONTEXT_TAGS), 17)
        self.assertEqual(len(rwo.DOCUMENT_TYPE_TAGS), 31)
        self.assertEqual(len(rwo.RELATIONSHIP_TAGS), 3)
        self.assertEqual(len(rwo.ALL_APPROVED_TAGS), 51)
        for tag in rwo.ALL_APPROVED_TAGS:
            self.assertIn(f"- {tag} — ", rwo.SYSTEM_PROMPT)

    def test_load_document_direct_utf8_text(self) -> None:
        doc_path = self.root / "notes.md"
        _ = doc_path.write_text("# Quarterly Review\nDate: 2026-10-15\nRevenue grew 18%.", encoding="utf-8")

        doc = rwo.load_document_direct(doc_path)
        self.assertEqual(doc.kind, "text")
        self.assertIn("Quarterly Review", doc.content)
        self.assertEqual(doc.images, [])
        self.assertEqual(doc.extension, ".md")

    def test_load_document_direct_image(self) -> None:
        img_path = self.root / "scan.png"
        fake_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
        _ = img_path.write_bytes(fake_png)

        doc = rwo.load_document_direct(img_path)
        self.assertEqual(doc.kind, "image")
        self.assertEqual(doc.content, "")
        self.assertEqual(doc.images, [base64.b64encode(fake_png).decode("ascii")])
        self.assertEqual(doc.extension, ".png")

    def test_extract_pdf_digital_text(self) -> None:
        pdf_path = self.root / "statement.pdf"
        _create_minimal_text_pdf(
            pdf_path,
            "Acme Bank Monthly Account Statement - October 20, 2026 - Closing Balance $14,250.00",
        )
        doc = rwo.load_document_direct(pdf_path)
        self.assertEqual(doc.kind, "text")
        self.assertIn("Acme Bank Monthly Account Statement", doc.content)
        self.assertEqual(doc.extension, ".pdf")

    def test_extract_pdf_scanned_fallback_to_vision_images(self) -> None:
        pdf_path = self.root / "scanned_receipt.pdf"
        _create_minimal_blank_pdf(pdf_path)
        doc = rwo.load_document_direct(pdf_path)
        self.assertEqual(doc.kind, "image")
        self.assertGreaterEqual(len(doc.images), 1)
        self.assertTrue(base64.b64decode(doc.images[0]).startswith(b"\x89PNG"))
        self.assertEqual(doc.extension, ".pdf")

    def test_extract_docx_and_rtf(self) -> None:
        rtf_path = self.root / "agreement.rtf"
        _ = rtf_path.write_text(
            r"{\rtf1\ansi\deff0 {\b Master Services Agreement} dated 2026-09-01 between Acme and Beta.}",
            encoding="utf-8",
        )
        doc_rtf = rwo.load_document_direct(rtf_path)
        self.assertEqual(doc_rtf.kind, "text")
        self.assertIn("Master Services Agreement", doc_rtf.content)

        docx_path = self.root / "proposal.docx"
        _ = subprocess.run(
            ["/usr/bin/textutil", "-convert", "docx", str(rtf_path), "-output", str(docx_path)],
            check=True,
        )
        doc_docx = rwo.load_document_direct(docx_path)
        self.assertEqual(doc_docx.kind, "text")
        self.assertIn("Master Services Agreement", doc_docx.content)
        self.assertEqual(doc_docx.extension, ".docx")

    def test_extract_xlsx_spreadsheet(self) -> None:
        xlsx_path = self.root / "budget.xlsx"
        with zipfile.ZipFile(xlsx_path, "w") as zf:
            zf.writestr(
                "xl/sharedStrings.xml",
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                "<si><t>Category</t></si>"
                "<si><t>Planned Spend</t></si>"
                "<si><t>Cloud Hosting</t></si>"
                "</sst>",
            )
            zf.writestr(
                "xl/_rels/workbook.xml.rels",
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/>'
                "</Relationships>",
            )
            zf.writestr(
                "xl/workbook.xml",
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                '<sheets><sheet name="2026 Annual Budget" sheetId="1" r:id="rId1"/></sheets>'
                "</workbook>",
            )
            zf.writestr(
                "xl/worksheets/sheet1.xml",
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                "<sheetData>"
                '<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row>'
                '<row r="2"><c r="A2" t="s"><v>2</v></c><c r="B2"><v>48000</v></c></row>'
                "</sheetData>"
                "</worksheet>",
            )

        doc = rwo.load_document_direct(xlsx_path)
        self.assertEqual(doc.kind, "text")
        self.assertIn("[Sheet: 2026 Annual Budget]", doc.content)
        self.assertIn("Category | Planned Spend", doc.content)
        self.assertIn("Cloud Hosting | 48000", doc.content)

    def test_extract_pptx_presentation(self) -> None:
        pptx_path = self.root / "deck.pptx"
        with zipfile.ZipFile(pptx_path, "w") as zf:
            zf.writestr(
                "ppt/slides/slide1.xml",
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
                'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
                "<a:p><a:r><a:t>Zero Trust Network Architecture Webinar</a:t></a:r></a:p>"
                "<a:p><a:r><a:t>October 20, 2026</a:t></a:r></a:p>"
                "</p:sld>",
            )
            zf.writestr(
                "ppt/notesSlides/notesSlide1.xml",
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<p:notes xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
                'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
                "<a:p><a:r><a:t>Welcome attendees to the security architecture webinar.</a:t></a:r></a:p>"
                "</p:notes>",
            )

        doc = rwo.load_document_direct(pptx_path)
        self.assertEqual(doc.kind, "text")
        self.assertIn("[Slide 1]", doc.content)
        self.assertIn("Zero Trust Network Architecture Webinar", doc.content)
        self.assertIn("[Slide 1 Notes]", doc.content)
        self.assertIn("Welcome attendees", doc.content)

    def test_extract_epub_ebook(self) -> None:
        epub_path = self.root / "book991.epub"
        with zipfile.ZipFile(epub_path, "w") as zf:
            zf.writestr(
                "META-INF/container.xml",
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                "<rootfiles>"
                '<rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
                "</rootfiles>"
                "</container>",
            )
            zf.writestr(
                "OEBPS/content.opf",
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<package xmlns="http://www.idpf.org/2007/opf" '
                'xmlns:dc="http://purl.org/dc/elements/1.1/" version="3.0">'
                "<metadata>"
                "<dc:title>Distributed Systems Engineering Guide</dc:title>"
                "<dc:creator>Dr. Elena Vance</dc:creator>"
                "<dc:date>2026-04-10</dc:date>"
                "</metadata>"
                "<manifest>"
                '<item id="ch1" href="chapter1.xhtml" media-type="application/xhtml+xml"/>'
                "</manifest>"
                "<spine>"
                '<itemref idref="ch1"/>'
                "</spine>"
                "</package>",
            )
            zf.writestr(
                "OEBPS/chapter1.xhtml",
                "<html><head><title>Ignored</title></head>"
                "<body><h1>Chapter 1: Consensus Protocols</h1>"
                "<p>This guide explains Raft and Paxos state machine replication.</p></body></html>",
            )

        doc = rwo.load_document_direct(epub_path)
        self.assertEqual(doc.kind, "text")
        self.assertIn("[EPUB Metadata]", doc.content)
        self.assertIn("Title: Distributed Systems Engineering Guide", doc.content)
        self.assertIn("Date: 2026-04-10", doc.content)
        self.assertIn("Chapter 1: Consensus Protocols", doc.content)
        self.assertEqual(doc.extension, ".epub")

    def test_rejects_apple_iwork_and_arbitrary_binaries(self) -> None:
        for ext in (".pages", ".numbers", ".key"):
            iwork_path = self.root / f"sample{ext}"
            _ = iwork_path.write_bytes(b"PK\x03\x04...")
            with self.assertRaises(rwo.UnsupportedDocumentError):
                _ = rwo.load_document_direct(iwork_path)

        bin_path = self.root / "mystery.dat"
        _ = bin_path.write_bytes(b"hello\x00world\x00binary")
        with self.assertRaises(rwo.UnsupportedDocumentError):
            _ = rwo.load_document_direct(bin_path)

    def test_format_new_filename_with_date(self) -> None:
        name = rwo.format_new_filename("2026-10-20", "Q3 Financial Summary", ".md")
        self.assertEqual(name, "2026-10-20 - Q3 Financial Summary.md")

    def test_format_new_filename_without_date(self) -> None:
        name = rwo.format_new_filename(None, "Project Apollo Architecture Guide", ".txt")
        self.assertEqual(name, "Project Apollo Architecture Guide.txt")

    def test_format_new_filename_deduplicates_date_and_extension(self) -> None:
        name = rwo.format_new_filename(
            "2026-10-20",
            "2026-10-20 - Acme Service Agreement.md",
            ".md",
        )
        self.assertEqual(name, "2026-10-20 - Acme Service Agreement.md")

    def test_format_new_filename_sanitizes_illegal_characters(self) -> None:
        name = rwo.format_new_filename(
            "2026-03-05",
            'Invoice: Q1/Q2 Consulting "Services"',
            ".txt",
        )
        self.assertEqual(name, "2026-03-05 - Invoice - Q1 - Q2 Consulting \"Services\".txt")

    def test_rename_file_safely_handles_collisions(self) -> None:
        existing = self.root / "2026-10-20 - Q3 Financial Summary.md"
        _ = existing.write_text("existing file", encoding="utf-8")

        source = self.root / "untitled.md"
        _ = source.write_text("new file", encoding="utf-8")

        renamed = rwo.rename_file_safely(source, "2026-10-20 - Q3 Financial Summary.md")
        self.assertEqual(renamed.name, "2026-10-20 - Q3 Financial Summary (2).md")
        self.assertTrue(renamed.exists())
        self.assertTrue(existing.exists())
        self.assertEqual(existing.read_text(encoding="utf-8"), "existing file")
        self.assertEqual(renamed.read_text(encoding="utf-8"), "new file")

    def test_validate_tags_accepts_valid_combinations_and_empty(self) -> None:
        self.assertEqual(
            rwo.validate_tags(["finance", "subscriptions", "invoice"]),
            ["finance", "subscriptions", "invoice"],
        )
        self.assertEqual(rwo.validate_tags([]), [])
        self.assertEqual(
            rwo.validate_tags(
                ["career", "interview", "transcript", "received"],
                trusted_provenance=["received"],
            ),
            ["career", "interview", "transcript", "received"],
        )

    def test_validate_tags_rejects_wrong_types_and_unapproved_values(self) -> None:
        bad_inputs: list[object] = [
            None,
            "finance",
            {"tags": ["finance"]},
            [123],
            ["Finance"],
            ["paid"],
            ["to-read"],
        ]
        for bad_input in bad_inputs:
            with self.assertRaises(rwo.TagValidationError):
                _ = rwo.validate_tags(bad_input)

    def test_validate_tags_rejects_duplicates(self) -> None:
        with self.assertRaises(rwo.TagValidationError):
            _ = rwo.validate_tags(["finance", "invoice", "finance"])

    def test_validate_tags_enforces_category_and_total_limits(self) -> None:
        with self.assertRaises(rwo.TagValidationError):
            _ = rwo.validate_tags(["finance", "tax", "legal"])

        with self.assertRaises(rwo.TagValidationError):
            _ = rwo.validate_tags(["invoice", "receipt", "statement"])

        with self.assertRaises(rwo.TagValidationError):
            _ = rwo.validate_tags(
                ["finance", "subscriptions", "invoice", "receipt", "received", "self-created"],
                trusted_provenance=["received", "self-created"],
            )

    def test_validate_tags_enforces_provenance_for_relationship_tags(self) -> None:
        for rel_tag in ("received", "sent", "self-created"):
            with self.assertRaises(rwo.TagValidationError):
                _ = rwo.validate_tags(["finance", "invoice", rel_tag])

        self.assertEqual(
            rwo.validate_tags(
                ["finance", "invoice", "received", "sent"],
                trusted_provenance=["received", "sent"],
            ),
            ["finance", "invoice", "received", "sent"],
        )

    def test_finder_tags_preserve_existing_and_avoid_duplicates(self) -> None:
        doc_path = self.root / "sample.txt"
        _ = doc_path.write_text("Sample content", encoding="utf-8")

        initial_user_tags = [
            "Important\n6",
            "paid",
            "acme-project",
            "custom-4",
            "custom-5",
            "finance\n4",
        ]
        rwo.write_finder_tags(doc_path, initial_user_tags)
        self.assertEqual(rwo.read_finder_tags(doc_path), initial_user_tags)

        # Apply validated tags:
        # - 'finance' is configured as Green in tag_colors -> 'finance\n2'
        # - 'subscriptions' is a Context tag (colored Green -> 'subscriptions\n2')
        # - 'invoice' is a Document-Type tag (colorless -> 'invoice\n0')
        # - custom user tags ('Important\n6', 'paid', 'acme-project', etc.) are preserved
        final_base_tags = rwo.apply_finder_tags(doc_path, ["finance", "subscriptions", "invoice"])
        raw_stored_tags = rwo.read_finder_tags(doc_path)

        self.assertEqual(
            raw_stored_tags,
            [
                "Important\n6",
                "paid",
                "acme-project",
                "custom-4",
                "custom-5",
                "finance\n2",
                "subscriptions\n2",
                "invoice\n0",
            ],
        )
        self.assertEqual(
            final_base_tags,
            [
                "Important",
                "paid",
                "acme-project",
                "custom-4",
                "custom-5",
                "finance",
                "subscriptions",
                "invoice",
            ],
        )

        _ = rwo.apply_finder_tags(doc_path, ["finance", "subscriptions", "invoice"])
        self.assertEqual(rwo.read_finder_tags(doc_path), raw_stored_tags)

    def test_parse_model_json_handles_fences_and_null_date(self) -> None:
        raw = '```json\n{"date": null, "title": "System Onboarding Checklist", "tags": ["technology", "checklist"]}\n```'
        result = rwo.parse_model_json(raw)
        self.assertIsNone(result.date)
        self.assertEqual(result.title, "System Onboarding Checklist")
        self.assertEqual(result.tags, ["technology", "checklist"])

    @patch("smart_rename.classify_document")
    def test_process_file_end_to_end_mocked(self, mock_classify: MagicMock) -> None:
        mock_classify.return_value = rwo.ClassificationResult(
            date="2026-10-20",
            title="Board Meeting Minutes",
            tags=["business", "meeting-notes"],
        )
        src = self.root / "doc1.txt"
        _ = src.write_text("Board Meeting on October 20, 2026...", encoding="utf-8")
        rwo.write_finder_tags(src, ["keep-me"])

        new_path, tags = rwo.process_file(src, quiet=True)
        self.assertEqual(new_path.name, "2026-10-20 - Board Meeting Minutes.txt")
        self.assertEqual(tags, ["business", "meeting-notes"])
        self.assertTrue(new_path.exists())
        self.assertFalse(src.exists())
        self.assertEqual(
            rwo.read_finder_tags(new_path),
            ["keep-me", "business\n7", "meeting-notes\n0"],
        )

    @patch("smart_rename.classify_document")
    def test_process_file_rejects_invalid_tagging_response_without_modifying_file(
        self,
        mock_classify: MagicMock,
    ) -> None:
        mock_classify.side_effect = rwo.TagValidationError("Unapproved tag 'invalid-tag'")
        src = self.root / "doc2.txt"
        _ = src.write_text("Some content", encoding="utf-8")
        rwo.write_finder_tags(src, ["existing-tag"])

        with self.assertRaises(rwo.TagValidationError):
            _ = rwo.process_file(src, quiet=True)

        self.assertTrue(src.exists())
        self.assertEqual(rwo.read_finder_tags(src), ["existing-tag"])

    def test_custom_external_config_dir_and_tag_colors(self) -> None:
        cfg_dir = self.root / "custom_config"
        cfg_dir.mkdir()
        _ = (cfg_dir / "settings.json").write_text(
            '{"ollama": {"host": "http://127.0.0.1:11434", "model": "custom-model:7b", "temperature": 0.2, "think": false, "timeout_seconds": 30}, '
            '"limits": {"max_filename_stem_chars": 50}, '
            '"extensions": {"supported_images": [".png"], "pdf": [".pdf"], "word_and_richtext": [".docx"], "spreadsheets": [".xlsx"], "presentations": [".pptx"], "ebooks": [".epub"], "unsupported_binaries": [".pages"]}}',
            encoding="utf-8",
        )
        _ = (cfg_dir / "tags.json").write_text(
            '{"limits": {"max_context_tags": 1, "max_document_type_tags": 1, "max_total_tags": 2}, '
            '"context_tags": {"finance": "Money docs"}, '
            '"document_type_tags": {"invoice": "Bill"}, '
            '"relationship_tags": {"received": "From external"}, '
            '"tag_colors": {"finance": "green"}}',
            encoding="utf-8",
        )
        _ = (cfg_dir / "system_prompt.md").write_text(
            "Custom Prompt ({{CONTEXT_TAG_COUNT}}):\n{{CONTEXT_TAGS_LIST}}\n{{DOCUMENT_TYPE_TAGS_LIST}}",
            encoding="utf-8",
        )

        custom_cfg = rwo.load_config(cfg_dir)
        self.assertEqual(custom_cfg.ollama_model, "custom-model:7b")
        self.assertEqual(custom_cfg.max_context_tags, 1)
        self.assertIn("- finance — Money docs", custom_cfg.system_prompt)
        self.assertEqual(custom_cfg.tag_colors, {"finance": 2})

        # Validate against custom limits (max 1 context tag)
        self.assertEqual(
            rwo.validate_tags(["finance", "invoice"], config=custom_cfg),
            ["finance", "invoice"],
        )

        # Verify tag_colors ("finance": "green" -> "finance\n2") is applied to Finder xattr
        doc_path = self.root / "bill.txt"
        _ = doc_path.write_text("Bill content", encoding="utf-8")
        _ = rwo.apply_finder_tags(doc_path, ["finance", "invoice"], config=custom_cfg)
        self.assertEqual(rwo.read_finder_tags(doc_path), ["finance\n2", "invoice\n0"])

    def test_naming_style_variations(self) -> None:
        self.assertEqual(
            rwo.format_new_filename("2026-10-20", "Q3 Financial Summary", ".pdf", naming_style="title_case"),
            "Q3 Financial Summary.pdf",
        )
        self.assertEqual(
            rwo.format_new_filename("2026-10-20", "Q3 Financial Summary", ".pdf", naming_style="date_kebab_case"),
            "2026-10-20-q3-financial-summary.pdf",
        )
        self.assertEqual(
            rwo.format_new_filename("2026-10-20", "Q3 Financial Summary", ".pdf", naming_style="kebab_case"),
            "q3-financial-summary.pdf",
        )
        self.assertEqual(
            rwo.format_new_filename("2026-10-20", "Q3 Financial Summary", ".pdf", naming_style="snake_case"),
            "q3_financial_summary.pdf",
        )

    def test_example_documents_in_repo_are_all_extractable(self) -> None:
        examples_dir = Path(__file__).resolve().parent.parent / "examples"
        expected_files = [
            "sample_subscription_invoice.txt",
            "sample_architecture_spec.md",
            "sample_quarterly_report.pdf",
            "sample_service_agreement.docx",
            "sample_annual_budget.xlsx",
            "sample_webinar_slides.pptx",
            "sample_distributed_systems_guide.epub",
        ]
        for fname in expected_files:
            fpath = examples_dir / fname
            self.assertTrue(fpath.is_file(), f"Missing example file: {fpath}")
            doc = rwo.load_document_direct(fpath)
            self.assertEqual(doc.kind, "text")
            self.assertGreater(len(doc.content), 20)

    def test_install_script_creates_config_without_overwriting_and_builds_workflow(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        install_script = repo_root / "install.sh"
        target_cfg = self.root / "gen_config"

        # 1. First run creates settings.json, tags.json, and system_prompt.md from config.example/
        proc1 = subprocess.run(
            [str(install_script), "--no-service-install", f"--config-dir={target_cfg}"],
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertIn("Created default settings.json", proc1.stdout)
        self.assertTrue((target_cfg / "settings.json").is_file())
        self.assertTrue((target_cfg / "tags.json").is_file())
        self.assertTrue((target_cfg / "system_prompt.md").is_file())

        # 2. Modify settings.json and verify a second run preserves user changes
        _ = (target_cfg / "settings.json").write_text('{"custom": true}\n', encoding="utf-8")
        proc2 = subprocess.run(
            [str(install_script), "--no-service-install", f"--config-dir={target_cfg}"],
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertIn("Kept existing settings.json", proc2.stdout)
        self.assertEqual((target_cfg / "settings.json").read_text(encoding="utf-8"), '{"custom": true}\n')

        # 3. Validate the generated Smart Rename.workflow bundle plists
        wf_out = repo_root / "Smart Rename.workflow"
        info_bytes = (wf_out / "Contents" / "Info.plist").read_bytes()
        info_plist = plistlib.loads(info_bytes)
        self.assertEqual(info_plist["NSServices"][0]["NSMenuItem"]["default"], "Smart Rename")
        wflow_bytes = (wf_out / "Contents" / "document.wflow").read_bytes()
        wflow_plist = plistlib.loads(wflow_bytes)
        wflow_content = wflow_bytes.decode("utf-8")
        self.assertIn("smart_rename.py", wflow_content)
        self.assertNotIn("{{SCRIPT_PATH}}", wflow_content)
        self.assertIsInstance(wflow_plist, dict)

    def test_date_normalization_and_fallback_extraction(self) -> None:
        self.assertEqual(rwo.normalize_date_string("2026-10-20"), "2026-10-20")
        self.assertEqual(rwo.normalize_date_string("20261020"), "2026-10-20")
        self.assertEqual(rwo.normalize_date_string("2026/10/8"), "2026-10-08")
        self.assertEqual(rwo.normalize_date_string("October 20, 2026"), "2026-10-20")
        self.assertEqual(rwo.normalize_date_string("20 Oct 2026"), "2026-10-20")

        # Fallback from filename (ISO and compact YYYYMMDD)
        self.assertEqual(
            rwo.extract_fallback_date("2026-10-20 - Cloud Security Architecture Webinar.txt", ""),
            "2026-10-20",
        )
        self.assertEqual(
            rwo.extract_fallback_date("20261014 0930 - Product Strategy Meeting Transcript.txt", ""),
            "2026-10-14",
        )
        # Fallback from document header when filename has no date
        self.assertEqual(
            rwo.extract_fallback_date("notes.txt", "Meeting Notes\nDate: October 15, 2026\nAttendees: Team"),
            "2026-10-15",
        )

    def test_icloud_fileprovider_tags_omit_per_file_color_suffixes(self) -> None:
        doc_path = self.root / "icloud_doc.txt"
        _ = doc_path.write_text("Invoice content", encoding="utf-8")

        # Simulate a file inside iCloud Drive that previously had corrupted Gray (\n1) tags
        rwo.write_finder_tags(doc_path, ["finance\n1", "invoice\n1"])
        with patch("smart_rename.is_fileprovider_path", return_value=True):
            applied = rwo.apply_finder_tags(doc_path, ["finance", "subscriptions", "invoice"])

        self.assertEqual(applied, ["finance", "invoice", "subscriptions"])
        # On FileProvider / iCloud Drive paths, plain tag names (without \n<color>) are written
        # so fileproviderd/bird does not overwrite them with \n1 (Gray).
        self.assertEqual(
            rwo.read_finder_tags(doc_path),
            ["finance", "invoice", "subscriptions"],
        )


if __name__ == "__main__":
    _ = unittest.main()

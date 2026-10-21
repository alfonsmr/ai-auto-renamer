# Example Documents for Testing — AI Auto Renamer (`Smart Rename`)

This folder contains **7 synthetic, non-personal documents** designed to test **AI Auto Renamer** (**`Smart Rename`**) safely out of the box without using personal files. All names, organizations (`CloudTools Inc.`, `Northwind Cloud`, `Contoso Ltd.`, `Pioneer Labs`), and numbers in these files are fictional and safe for public repositories.

---

## 1. Included Sample Files & What Each One Tests

Each file exercises a different local document extractor, date-detection pattern (explicit date vs. dateless), and multi-tag combination from the controlled vocabulary in [`config.example/tags.example.json`](../config.example/tags.example.json):

| Original File | Format | What It Tests Under the Hood | Expected New Filename (Approx.) | Expected Tags & Finder Dot Colors |
| :--- | :--- | :--- | :--- | :--- |
| `sample_subscription_invoice.txt` | Plain Text (`.txt`) | Direct UTF-8 text loader; written date normalization (`October 12, 2026` → `2026-10-12`); avoids false-positive `tax` or `technology` tags on a software bill | `2026-10-12 - CloudTools Annual Subscription Invoice.txt` | 🟢 `finance`, 🟢 `subscriptions`, `invoice` |
| `sample_architecture_spec.md` | Markdown (`.md`) | Direct UTF-8 Markdown loader; **dateless document handling** (`date: null` → clean Title Case name without a date prefix) | `OAuth 2.0 PKCE Token Refresh Flow Specification.md` | 🔵 `technology`, `specification` |
| `sample_quarterly_report.pdf` | PDF (`.pdf`) | Digital PDF extraction via `pdftotext` + `pdfinfo`; ISO date (`2026-10-18`); multi-domain Context tags (`finance` + `technology`) | `2026-10-18 - Northwind Cloud Q3 Financial Report.pdf` | 🟢 `finance`, 🔵 `technology`, `report` |
| `sample_service_agreement.docx` | Word (`.docx`) | Word extraction via macOS `/usr/bin/textutil` (with native `word/document.xml` ZIP/XML fallback); written effective date (`September 15, 2026` → `2026-09-15`) | `2026-09-15 - Master Consulting Services Agreement.docx` | 🟣 `legal`, 🟠 `business`, `contract` |
| `sample_annual_budget.xlsx` | Excel (`.xlsx`) | Native Python `.xlsx` ZIP/XML parser (`xl/workbook.xml`, `xl/sharedStrings.xml`, worksheet cells); fiscal-year title (`FY2026`) without a specific calendar day (`date: null`) | `FY2026 Engineering Budget.xlsx` | 🟢 `finance`, 🔵 `technology`, `budget` |
| `sample_webinar_slides.pptx` | PowerPoint (`.pptx`) | Native Python `.pptx` ZIP/XML parser extracting both slide text (`ppt/slides/slide1.xml`) and speaker notes (`ppt/notesSlides/notesSlide1.xml`) | `2026-10-20 - Zero Trust Cloud Security Architecture Webinar.pptx` | 🔵 `technology`, `webinar`, `presentation` |
| `sample_distributed_systems_guide.epub` | E-Book (`.epub`) | Native Python `.epub` parser extracting Dublin Core OPF metadata (`dc:title`, `dc:creator`, `dc:date`) and XHTML chapter content | `2026-04-10 - Distributed Systems Engineering Handbook.epub` | 🔵 `technology`, 🟡 `learning`, `guide` |

> [!NOTE]
> **Why do some tags have colored dots (🟢, 🔵, 🟣, 🟠, 🟡) while others do not?**
> By design, **AI Auto Renamer** uses a **Domain At-a-Glance Color Schema**:
> - **Context tags** (`finance`, `subscriptions`, `technology`, `legal`, `business`, `learning`, etc.) represent high-level domains and are assigned **macOS Finder colors** (🟢 Green, 🔵 Blue, 🟣 Purple, 🟠 Orange, 🟡 Yellow, 🔴 Red, ⚪️ Gray) and synced to Finder's left sidebar.
> - **Document-Type tags** (`invoice`, `specification`, `report`, `contract`, `budget`, `webinar`, `presentation`, `guide`, etc.) are intentionally **colorless** so files don't display a cluttered rainbow of dots in Finder list view, while remaining 100% searchable in Finder and Spotlight (e.g., `tag:invoice`, `tag:contract`, `tag:guide`).
>
> *(Note: Image files such as `.png`, `.jpg`, `.webp`, and scanned/image-only PDFs are also supported via local Ollama Vision.)*

---

## 2. How to Test Offline (No Ollama Required)

If you want to verify that all 7 example files extract cleanly and that tag validation, date normalization, and Finder extended attributes (`xattr`) work before starting Ollama, run the automated unit test suite from the repository root:

```bash
/usr/bin/python3 -m unittest discover -s tests -v
```

*(Specifically, `test_example_documents_in_repo_are_all_extractable` validates local content extraction across all 7 files in this folder.)*

---

## 3. How to Test With Ollama Without Modifying These Files (`--dry-run`)

Make sure [Ollama](https://ollama.com/) is running locally (`ollama pull gemma4:26b`, and `brew install poppler` for PDF extraction). From the repository root, run:

```bash
/usr/bin/python3 smart_rename.py --dry-run examples/sample_*
```

This prints the proposed filename and validated tags for each sample document without renaming or tagging the tracked files in `examples/`:

```text
[DRY RUN] sample_annual_budget.xlsx -> FY2026 Engineering Budget.xlsx | tags=["finance", "technology", "budget"]
[DRY RUN] sample_architecture_spec.md -> OAuth 2.0 PKCE Token Refresh Flow Specification.md | tags=["technology", "specification"]
[DRY RUN] sample_distributed_systems_guide.epub -> 2026-04-10 - Distributed Systems Engineering Handbook.epub | tags=["technology", "learning", "guide"]
[DRY RUN] sample_quarterly_report.pdf -> 2026-10-18 - Northwind Cloud Q3 Financial Report.pdf | tags=["finance", "technology", "report"]
[DRY RUN] sample_service_agreement.docx -> 2026-09-15 - Master Consulting Services Agreement.docx | tags=["legal", "business", "contract"]
[DRY RUN] sample_subscription_invoice.txt -> 2026-10-12 - CloudTools Annual Subscription Invoice.txt | tags=["finance", "subscriptions", "invoice"]
[DRY RUN] sample_webinar_slides.pptx -> 2026-10-20 - Zero Trust Cloud Security Architecture Webinar.pptx | tags=["technology", "webinar", "presentation"]
```

### Useful CLI Variations to Try on the Examples
- **Test with a different local Ollama model:**
  ```bash
  /usr/bin/python3 smart_rename.py --dry-run --model gemma3:12b examples/sample_*
  ```
- **Test relationship tags (`received`, `sent`, `self-created`) using trusted provenance:**
  *(By default, relationship tags are blocked unless explicit provenance is supplied.)*
  ```bash
  /usr/bin/python3 smart_rename.py --dry-run --provenance received examples/sample_subscription_invoice.txt
  ```

---

## 4. How to Test Real In-Place Renaming & Finder Tag Colors

To test actual file renaming and colored Finder dots **without altering the tracked files in this Git repository**, copy the samples to a temporary folder (such as `/tmp/ollama-test` or a test folder in Finder/iCloud Drive) first:

```bash
# 1. Make sure you have run ./install.sh once from the repo root to install the Quick Action & sync Finder tags:
./install.sh

# 2. Copy the 7 sample documents to a temporary test directory and open it in Finder:
rm -rf /tmp/ollama-test
mkdir -p /tmp/ollama-test
cp examples/sample_* /tmp/ollama-test/
open /tmp/ollama-test
```

Then in the **Finder** window that opens:
1. *(First time only)* Right-click any file, go to **Quick Actions → Customize...**, and enable **Smart Rename** (macOS does not enable newly installed Quick Actions by default).
2. Select all 7 files, **Right-Click → Quick Actions → Smart Rename**
   *(or run `/usr/bin/python3 smart_rename.py /tmp/ollama-test/*` in Terminal)*.
3. Watch the files rename in place and display their domain color dots (🟢 Green for Finance/Subscriptions, 🔵 Blue for Technology, 🟣 Purple for Legal, 🟠 Orange for Business, 🟡 Yellow for Learning) alongside their searchable Document-Type tags (`invoice`, `specification`, `report`, `contract`, `budget`, `webinar`, `presentation`, `guide`).

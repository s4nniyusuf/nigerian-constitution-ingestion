"""Extracts the Nigerian Constitution into complete legal-section records"""
import argparse
import hashlib
import json
import re
from pathlib import Path

import pymupdf

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PDF = PROJECT_ROOT / "Constitution-of-the-Federal-Republic-of-Nigeria-2023.pdf"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "processed"
# PDF viewer page 23 is PyMuPDF's zero-based page index 22.
START_PAGE_INDEX = 22


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


RUNNING_HEADER = re.compile(
    r"^(?:\d{1,3}\s+)?The Constitution of the Federal Republic of Nigeria Updated with the First, Second, Third, Fourth and Fifth Alterations(?:\s+\d{1,3})?$",
    re.IGNORECASE,
)


def norm(text):
    text = (text or "").replace("\x00", "").replace("\u00ad", "")
    text = text.replace("\ufb01", "fi").replace("\ufb02", "fl")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    # This publication header is repeated in page content and is not part of
    # the constitutional provision. Remove it before structural parsing.
    lines = [line for line in lines if not RUNNING_HEADER.fullmatch(line)]
    return "\n".join(lines).strip()


def inspect(path):
    rows = []
    with pymupdf.open(path) as doc:
        for i, page in enumerate(doc):
            text = page.get_text("text", sort=True) or ""
            rows.append({"physical_page": i + 1, "pymupdf_page_index": i,
                         "included_in_ingestion": i >= START_PAGE_INDEX,
                         "char_count": len(text.strip()), "word_count": len(text.split()),
                         "image_count": len(page.get_images(full=True)),
                         "needs_review": i >= START_PAGE_INDEX and len(text.strip()) < 80})
        return {"path": str(path), "sha256": sha256(path), "page_count": len(doc),
                "start_page_index": START_PAGE_INDEX, "start_physical_page": START_PAGE_INDEX + 1,
                "pages_with_text": sum(r["char_count"] >= 80 for r in rows),
                "pages_for_review": sum(r["needs_review"] for r in rows), "pages": rows}


def ocr_page(page, dpi):
    try:
        import io
        import pytesseract
        from PIL import Image
        pix = page.get_pixmap(matrix=pymupdf.Matrix(dpi / 72, dpi / 72), alpha=False)
        return pytesseract.image_to_string(Image.open(io.BytesIO(pix.tobytes("png"))),
                                           lang="eng", config="--psm 3"), None
    except Exception as exc:
        return None, str(exc)


def extract_pages(path, use_ocr=False, dpi=300, min_chars=80):
    """Extract only physical PDF pages 23 onward; page metadata remains 1-based."""
    doc_id = re.sub(r"[^a-zA-Z0-9]+", "-", path.stem).strip("-").lower()
    pages = []
    with pymupdf.open(path) as doc:
        if len(doc) <= START_PAGE_INDEX:
            raise ValueError(f"PDF has {len(doc)} pages; cannot start at PDF viewer page 23 (index 22).")
        for index in range(START_PAGE_INDEX, len(doc)):
            page = doc[index]
            native = page.get_text("text", sort=True) or ""
            chosen, method, error = native, "native_text", None
            if use_ocr and len(native.strip()) < min_chars:
                ocr_text, error = ocr_page(page, dpi)
                if ocr_text and len(ocr_text.strip()) > len(native.strip()):
                    chosen, method = ocr_text, "tesseract_ocr_fallback"
            pages.append({"document_id": doc_id, "source_file": path.name,
                          "physical_page": index + 1, "pymupdf_page_index": index,
                          "native_text": native, "extracted_text": chosen,
                          "clean_text": norm(chosen), "extraction_method": method,
                          "char_count": len(chosen.strip()), "word_count": len(chosen.split()),
                          "needs_review": len(chosen.strip()) < min_chars, "ocr_error": error,
                          "image_count": len(page.get_images(full=True))})
    return doc_id, pages


PREAMBLE_RE = re.compile(
    r"(WE\s*,?\s*the people\b.*?DO\s+HEREBY\s+MAKE,\s*ENACT\s+AND\s+GIVE\s+TO\s+OURSELVES\s+the\s+following\s+Constitution\s*:?)",
    re.IGNORECASE | re.DOTALL,
)
CHAPTER_RE = re.compile(r"^CHAPTER\s+([IVXLCDM]+)\s*$", re.IGNORECASE)
PART_RE = re.compile(r"^PART\s+([IVXLCDM]+)\s*$", re.IGNORECASE)
SECTION_RE = re.compile(r"^(\d{1,3}[A-Z]?)\.\s*(.{1,180})$")


def parse_structure(pages, doc_id, source):
    """Return preamble, complete numbered sections, and whole-schedule records."""
    records = []
    chapter = chapter_title = part = part_title = None
    current = None
    awaiting_chapter_title = False
    awaiting_part_title = False
    in_schedule = False

    def flush():
        nonlocal current
        if current and current["text"].strip():
            common = {
                "document_id": doc_id, "source_file": source,
                "record_type": current["type"],
                "physical_page_start": current["start"],
                "physical_page_end": current["end"],
                "chapter": current.get("chapter"),
                "chapter_title": current.get("chapter_title"),
                "part": current.get("part"), "part_title": current.get("part_title"),
                "section_number": current.get("number"),
                # Schedule titles belong only in schedule_title, not section_title.
                "section_title": current.get("title") if current["type"] == "section" else None,
                "text": current["text"].strip(), "record_index": len(records),
            }
            if current["type"] == "schedule":
                common["schedule_title"] = current.get("title")
            records.append(common)
        current = None

    first_page = pages[0] if pages else None
    if first_page:
        match = PREAMBLE_RE.search(first_page["clean_text"])
        if match:
            records.append({"document_id": doc_id, "source_file": source,
                            "record_type": "preamble",
                            "physical_page_start": first_page["physical_page"],
                            "physical_page_end": first_page["physical_page"],
                            "chapter": None, "chapter_title": None, "part": None,
                            "part_title": None, "section_number": None,
                            "section_title": None, "text": norm(match.group(1)),
                            "record_index": 0})
            first_page["clean_text"] = (first_page["clean_text"][:match.start()] + "\n" +
                                         first_page["clean_text"][match.end():]).strip()

    schedule_re = re.compile(r"^(FIRST|SECOND|THIRD|FOURTH|FIFTH|SIXTH|SEVENTH)\s+SCHEDULE\s*$", re.I)
    for page in pages:
        for line in page["clean_text"].splitlines():
            s = line.strip()
            if not s:
                if current:
                    current["text"] += "\n"
                continue

            sched = schedule_re.match(s)
            if sched:
                flush()
                in_schedule = True
                schedule_title = f"{sched.group(1).title()} Schedule"
                current = {"type": "schedule", "start": page["physical_page"],
                           "end": page["physical_page"], "title": schedule_title,
                           "number": None, "chapter": None, "chapter_title": None,
                           "part": None, "part_title": None, "text": s}
                awaiting_chapter_title = awaiting_part_title = False
                continue

            if in_schedule:
                current["text"] += "\n" + s
                current["end"] = page["physical_page"]
                continue

            cm = CHAPTER_RE.match(s)
            if cm:
                flush()
                chapter = f"Chapter {cm.group(1).upper()}"
                chapter_title = None
                part = part_title = None
                awaiting_chapter_title = True
                awaiting_part_title = False
                continue
            pm = PART_RE.match(s)
            if pm:
                flush()
                part = f"Part {pm.group(1).upper()}"
                part_title = None
                awaiting_part_title = True
                awaiting_chapter_title = False
                continue
            # Some amendment headings precede the actual section heading on
            # the same line, e.g. "[Section 76(1) is altered ...] 76. ...".
            # Use a cleaned candidate for detection but preserve the source line.
            heading_candidate = re.sub(r"^(?:\[[^\]]*\]\s*)+", "", s).strip()
            sm = SECTION_RE.match(heading_candidate)
            # Amendment notes can wrap across PDF lines, leaving only the
            # closing part of the note before the section heading on this line.
            # In that case, retry on the text following the final closing bracket.
            if not sm and "]" in s:
                after_annotation = s.rsplit("]", 1)[1].strip()
                sm = SECTION_RE.match(after_annotation)
            if sm:
                flush()
                current = {"type": "section", "start": page["physical_page"],
                           "end": page["physical_page"], "chapter": chapter,
                           "chapter_title": chapter_title, "part": part,
                           "part_title": part_title, "number": sm.group(1),
                           "title": sm.group(2).strip(), "text": s}
                awaiting_chapter_title = awaiting_part_title = False
                continue
            if awaiting_chapter_title:
                chapter_title = s
                awaiting_chapter_title = False
                continue
            if awaiting_part_title:
                part_title = s
                awaiting_part_title = False
                continue
            if current:
                current["text"] += "\n" + s
                current["end"] = page["physical_page"]

    flush()
    for idx, record in enumerate(records):
        record["record_index"] = idx
    return records


def write_jsonl(path, rows):
    with path.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")


def ingest(path, outdir, use_ocr=False, dpi=300, min_chars=80):
    outdir.mkdir(parents=True, exist_ok=True)
    doc_id, pages = extract_pages(path, use_ocr, dpi, min_chars)
    records = parse_structure(pages, doc_id, path.name)
    write_jsonl(outdir / "pages.jsonl", pages)
    write_jsonl(outdir / "legal_records.jsonl", records)
    review = [{k: p[k] for k in ("physical_page", "pymupdf_page_index", "char_count",
              "needs_review", "extraction_method", "ocr_error")} for p in pages if p["needs_review"]]
    (outdir / "review_pages.json").write_text(json.dumps(review, indent=2, ensure_ascii=False), encoding="utf-8")
    with pymupdf.open(path) as source_doc:
        pdf_page_count = len(source_doc)
    manifest = {"document_id": doc_id, "source_file": path.name, "sha256": sha256(path),
                "pdf_page_count": pdf_page_count, "ingestion_start_physical_page": START_PAGE_INDEX + 1,
                "ingestion_start_pymupdf_index": START_PAGE_INDEX, "pages_processed": len(pages),
                "pages_with_native_text": sum(bool(p["native_text"].strip()) for p in pages),
                "pages_using_ocr": sum(p["extraction_method"] == "tesseract_ocr_fallback" for p in pages),
                "pages_for_review": len(review), "legal_records": len(records),
                "preamble_records": sum(r["record_type"] == "preamble" for r in records),
                "section_records": sum(r["record_type"] == "section" for r in records),
                "schedule_records": sum(r["record_type"] == "schedule" for r in records),
                "chunking": False, "pipeline_version": "0.3.0"}
    (outdir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest


def resolve_pdf(value):
    path = Path(value) if value else DEFAULT_PDF
    if not path.is_absolute():
        candidate = PROJECT_ROOT / path
        path = candidate if candidate.exists() else path.resolve()
    if not path.is_file():
        raise FileNotFoundError(f"PDF not found: {path}\nCopy the Constitution PDF into {PROJECT_ROOT} or pass its path.")
    return path


def main():
    parser = argparse.ArgumentParser(description="Extract complete Nigerian constitutional sections without chunking.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    inspect_parser = sub.add_parser("inspect", help="Inspect the PDF and show which pages ingestion will include.")
    inspect_parser.add_argument("pdf", nargs="?", help="PDF path; defaults to the Constitution PDF in the project root.")
    ingest_parser = sub.add_parser("ingest", help="Extract pages and complete preamble/section records (no chunks).")
    ingest_parser.add_argument("pdf", nargs="?", help="PDF path; defaults to the Constitution PDF in the project root.")
    ingest_parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    ingest_parser.add_argument("--ocr", action="store_true", help="Use Tesseract as a fallback for short native text.")
    ingest_parser.add_argument("--ocr-dpi", type=int, default=300)
    ingest_parser.add_argument("--min-chars", type=int, default=80)
    args = parser.parse_args()
    try:
        pdf_path = resolve_pdf(args.pdf)
        if args.cmd == "inspect":
            result = inspect(pdf_path)
        else:
            output_dir = args.output_dir if args.output_dir.is_absolute() else PROJECT_ROOT / args.output_dir
            result = ingest(pdf_path, output_dir, args.ocr, args.ocr_dpi, args.min_chars)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except Exception as exc:
        parser.exit(1, f"Error: {exc}\n")


if __name__ == "__main__":
    main()

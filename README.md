# Nigerian Constitution: PDF Ingestion & Structural Parsing
A Python project that extracts text from a Nigerian Constitution PDF and
organizes it into structured JSONL files.

This project is the **data preparation stage** of a future
Retrieval-Augmented Generation (RAG) system. It prepares legal text for
a separate pipeline that will later split text into chunks, create
embeddings, and retrieve relevant information.



## What the project does

1.  Reads a PDF page by page.
2.  Extracts text using PyMuPDF.
3.  Cleans common PDF extraction artefacts, such as repeated running
    headers.
4.  Identifies legal structure, including the preamble,
    chapters, parts, numbered sections, and schedules.
5.  Saves page-level extraction data and structured legal records as
    JSONL.
6.  Flags pages that may need manual review, such as pages with very
    little extracted text or OCR errors.
7.  Writes a manifest containing information about the input PDF and
    ingestion run.

## What the project does not do

This project does **not**: 
- Split legal records into RAG chunks. 
- Generate embeddings. 
- Create or update a vector database. 
- Answer
legal questions. 
- Confirm that the supplied PDF is the latest or
legally authoritative version of the Constitution.

## Project structure

``` text
nigerian_law_rag_ingestion/
├── legal_ingest/
│   ├── __init__.py
│   └── cli.py
├── tests/
├── data/
│   └── processed/       # Generated output files
├── requirements.txt
├── .gitignore
└── README.md
```

<!-- The `data/processed/` directory contains generated output.  -->
<!-- The source
PDF and generated data may be excluded from version control, depending
on your `.gitignore`. -->

## Requirements

-   Python 3.10 or newer
-   The PDF you want to process
-   Tesseract OCR, only if you want to use the optional OCR feature

## 1. Set up the project

Open PowerShell in the project directory and run:

``` powershell
py -m venv .venv
.venv\Scripts\Activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 2. Add the PDF

Place the PDF in the project root and name it:

``` text
Constitution-of-the-Federal-Republic-of-Nigeria-2023.pdf
```

If your PDF has a different name or is stored elsewhere, pass its path
to the relevant command.

## 3. Inspect the PDF

Run the inspection command before ingestion:

``` powershell
python -m legal_ingest.cli inspect
```

To inspect a specific PDF:

``` powershell
python -m legal_ingest.cli inspect "C:\path\to\document.pdf"
```

The inspection command reports information such as page count, text
extraction coverage, image counts, and pages that may need review. A
page with little extracted text is not necessarily scanned; it is a
warning to check that page.

## 4. Run ingestion

``` powershell
python -m legal_ingest.cli ingest
```

To process a PDF at another path:

``` powershell
python -m legal_ingest.cli ingest "C:\path\to\document.pdf"
```

To choose an output directory:

``` powershell
python -m legal_ingest.cli ingest --output-dir data/processed
```

The default output directory is `data/processed/`, unless another
location is specified.

## 5. Optional OCR

OCR may help recover text from scanned pages or pages where normal PDF
text extraction returns very little text. It can still make mistakes,
especially with legal numbering, punctuation, and subsection labels.

Install the optional Python packages:

``` powershell
pip install pytesseract Pillow
```

You must also install the **Tesseract OCR application** separately and
make sure Windows can find `tesseract.exe` through your `PATH`.

Then run:

``` powershell
python -m legal_ingest.cli ingest --ocr
```

Review OCR output against the original PDF before using it.

## Output files

By default, output files are written to `data/processed/`.

### `pages.jsonl`

Contains page-level extraction data, with one JSON record per physical
PDF page. Depending on the extraction result, a record contains 
extracted text, cleaned text, extraction method, page number, and review
flags.

Use this file to investigate extraction problems and compare the text
with the original PDF.

### `legal_records.jsonl` (main data)

Contains the structured legal records recognized by the parser. A record
may represent the preamble, a numbered section, a schedule, or another
supported structural element.

The parser aims to keep each numbered section together with its
subsections and paragraphs. It does not split sections into RAG chunks.

Example of the field layout only; the values are illustrative :

``` json
{
  "document_id": "constitution-of-the-federal-republic-of-nigeria-2023",
  "source": "Constitution-of-the-Federal-Republic-of-Nigeria-2023.pdf",
  "physical_page_start": 45,
  "physical_page_end": 46,
  "chapter": "IV",
  "part": null,
  "section_number": "33",
  "section_title": "Right to life",
  "record_type": "section",
  "text": "Complete section text, including subsections...",
  "record_index": 0
}
```

The exact fields depend on the record type. For example, a schedule record has a `schedule_title` field instead of a numbered section title. Metadata is set to `null` when it does not apply or when the parser cannot identify
it.

### `review_pages.json`

Lists pages flagged for review, such as pages with little extracted text
or OCR errors. Inspect these pages in the original PDF to see whether
text is missing or incorrectly recognized.

### `manifest.json`

Summarizes the ingestion run. It includes information such as the
source PDF, its hash, page count, record counts, and whether chunking or
embeddings were performed.

Counts describe the output generated by that run. They do not prove that
every legal provision was found.

## Understanding page numbers

The `physical_page_start` and `physical_page_end` fields refer to
physical PDF page positions, counted from **1**. They may not match the
printed page numbers shown on the pages themselves.

## Data quality and validation

This is a rule-based parser. It uses text patterns to recognize legal
structure. Unusual formatting, wrapped headings, amendment notes, and
PDF reading-order problems can cause records to be missed or identified
incorrectly.

Before using the dataset in a RAG pipeline:

1.  Open `review_pages.json` and inspect flagged pages.
2.  Compare records with the original PDF, including records that span
    multiple pages.
3.  Look for missing or duplicated section identifiers.
4.  Confirm that each section includes its complete subsections and
    paragraphs.
5.  Check that chapter, part, section, and schedule metadata are
    assigned correctly.
6.  Investigate empty records, unexpected page ranges, and text that
    appears truncated.

Automated checks can identify structural problems, but they cannot
guarantee that the extracted text is complete, accurate, or legally
authoritative.

## Reproducibility

The output depends on the source PDF, parser code, Python environment,
and command-line options.

To reproduce a run, use the same PDF and project version with the same
options.

## Next step: use the data in a RAG pipeline

In a later stage:

1.  Load records from `legal_records.jsonl`.
2.  Choose a text-splitting strategy.
3.  Split records into chunks where necessary, preserving legal
    boundaries where possible.
4.  Carry useful metadata into each chunk, such as section number,
    title, chapter, and source page range.
5.  Generate embeddings and store the chunks in a vector database.
6.  Keep links back to the original record and PDF pages so retrieved
    passages can be checked against the source.

## Disclaimer

This project performs technical text extraction and structural parsing only.

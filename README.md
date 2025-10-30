
This repository demonstrates a simple, local document search system using Whoosh for indexing and Flask for serving search and document rendering. It supports text extraction from PDFs using either Poppler (pdftotext) or PyMuPDF (fitz), and stores searchable fields such as title, author, content, language and year.

This README explains:
- recommended tooling (Poppler, PyMuPDF)
- how to configure pdftotext if you use Poppler
- an alternative workflow using PyMuPDF for better structure
- a Whoosh schema and example indexing flow
- how to run a minimal Flask search + viewer server
- troubleshooting and tips for OCR and multilingual documents

---

## Quick summary

- Poppler `pdftotext` is a fast, battle-tested CLI for extracting textual content from PDFs. If you prefer a direct conversion to plain text or HTML, use Poppler.
- PyMuPDF (`fitz`) gives better control and structure (per-page extraction, images, bounding boxes) and is recommended when you need page-aware or layout-preserving extraction.
- Whoosh is a lightweight pure-Python full-text index that works well for small-to-medium collections and local use.
- Flask provides a small web UI to search the Whoosh index and render results (plain-text or PDF viewer).

---

## Prerequisites

- Python 3.8+ (3.10/3.11 recommended)
- pip
- (Optional) Poppler — to use `pdftotext`
  - Windows: download poppler-24.08.0 and link (poppler-24.08.0\Library\bin\pdftotext.exe) in your ini file programpath, this will convert pdf to text (store in a text file or html).
  - macOS: `brew install poppler`
  - Linux: `sudo apt-get install poppler-utils`
- (Optional but recommended) PyMuPDF: `pip install pymupdf`
- Whoosh: `pip install whoosh`
- Flask (for the UI): `pip install flask`
- (Optional) Tesseract OCR (if you need OCR for scanned PDFs): install OS package or binaries and configure the `tesseract_cmd` path for pytesseract.

---

## Installation

Create and activate a virtual environment, then install dependencies:

```bash
python -m venv venv
# macOS / Linux
source venv/bin/activate
# Windows (PowerShell)
.\venv\Scripts\Activate.ps1

pip install whoosh flask pymupdf langdetect pytesseract Pillow
# optionally install striprtf if you also handle RTFs
pip install striprtf
```

If you plan to use Poppler's `pdftotext`, download it and note the `pdftotext.exe` location on Windows or ensure `pdftotext` is in your PATH on macOS/Linux.

---

## Configuring pdftotext (Poppler) in an INI or config file

If your project reads an ini/config file for external tool paths, add an entry for the program path. Example `config.ini`:

```ini
[programs]
pdftotext_path = C:\tools\poppler-24.08.0\Library\bin\pdftotext.exe
tesseract_cmd = C:\Program Files\Tesseract-OCR\tesseract.exe
```

Example Python snippet to read it:

```python
from configparser import ConfigParser

cfg = ConfigParser()
cfg.read("config.ini")
pdftotext_path = cfg.get("programs", "pdftotext_path", fallback="pdftotext")
tesseract_cmd = cfg.get("programs", "tesseract_cmd", fallback=None)
```

If `pdftotext_path` points to an executable, use `subprocess` to call it and capture stdout into a text file.

---

## Two extraction options

### Option A — Poppler / pdftotext (simple, fast)
Good when PDF is mostly digital text and you want a quick plaintext or HTML output.

Example call:

```python
import subprocess
def pdftotext_extract(pdf_path, out_txt_path, pdftotext_bin="pdftotext"):
    # -layout preserves approximate layout; omit if you want linear text
    subprocess.run([pdftotext_bin, "-layout", pdf_path, out_txt_path], check=True)
```

You can store the resulting `.txt` or `.html` in a documents folder and index the text content.

### Option B — PyMuPDF / fitz (recommended for layout & pages)
PyMuPDF (import fitz) can be used to replace pdftotext for better pdf structure, you can now index your pdf with the fields (title, author, content, language, year) etc
Provides per-page extraction and lets you inspect if the page contains images only (so you can OCR).

Example PyMuPDF extraction:

```python
import fitz  # pip install pymupdf

def extract_pages_with_fitz(pdf_path):
    doc = fitz.open(pdf_path)
    for i, page in enumerate(doc, start=1):
        text = page.get_text("text")  # or "blocks", "dict", etc.
        yield i, text
```

If `text` is empty for a page, render the page to an image and OCR it with pytesseract.

---

## Whoosh: schema and example indexer

Example Whoosh schema (fields: title, author, content, language, year, filepath, filename):

```python
from whoosh import index
from whoosh.fields import Schema, TEXT, ID, KEYWORD, NUMERIC
import os

schema = Schema(
    filename=ID(stored=True),
    filepath=ID(stored=True),
    title=TEXT(stored=True),
    author=TEXT(stored=True),
    content=TEXT(stored=True),
    language=KEYWORD(stored=True),
    year=NUMERIC(stored=True)
)

if not os.path.exists("indexdir"):
    os.mkdir("indexdir")
ix = index.create_in("indexdir", schema)
```

Indexing example:

```python
from whoosh.writing import AsyncWriter
from langdetect import detect

def index_document(ix, pdf_path, metadata, full_text):
    writer = AsyncWriter(ix)
    language = "unknown"
    try:
        language = detect(full_text)
    except Exception:
        pass

    writer.add_document(
        filename=os.path.basename(pdf_path),
        filepath=pdf_path,
        title=metadata.get("title", ""),
        author=metadata.get("author", ""),
        content=full_text,
        language=language,
        year=metadata.get("year", 0)
    )
    writer.commit()
```

Notes:
- Use pagination-aware indexing when using PyMuPDF: create one Whoosh document per PDF page if you need page-level search.
- Tune analyzers/tokenizers if you have multilingual content.

---

## Minimal Flask search + viewer

A minimal Flask endpoint to search Whoosh and render results:

```python
from flask import Flask, request, render_template
from whoosh.qparser import MultifieldParser
from whoosh import index

app = Flask(__name__)
ix = index.open_dir("indexdir")

@app.route("/search")
def search():
    q = request.args.get("q", "")
    with ix.searcher() as s:
        parser = MultifieldParser(["title", "author", "content"], schema=ix.schema)
        qobj = parser.parse(q)
        results = s.search(qobj, limit=20)
        hits = [dict(hit) for hit in results]
    return render_template("results.html", results=hits)
```

Serving the original PDF for viewing/download:

```python
from flask import send_from_directory
@app.route("/docs/<path:filename>")
def docs(filename):
    return send_from_directory("pdfs", filename)
```

If you indexed pages separately, include `page_number` in the stored document and pass a parameter to the viewer to jump to the page (client-side PDF.js can do this with a `#page=3` fragment).

---

## OCR (pytesseract) fallback for scanned pages

If a page has no text from extraction, render it to PNG at high DPI and OCR:

```python
import pytesseract
from PIL import Image
import io

def ocr_page(page, dpi=300):
    pix = page.get_pixmap(dpi=dpi)
    img = Image.open(io.BytesIO(pix.tobytes("png")))
    return pytesseract.image_to_string(img)
```

Set `pytesseract.pytesseract.tesseract_cmd` on Windows to the Tesseract exe path.

---

## Tips & recommendations

- For best page-accurate indexing, convert RTF/DOC to PDF using LibreOffice or Word and then use PyMuPDF to extract pages.
- If you index entire PDFs as single documents, you'll lose precise page-level results.
- Whoosh is great for local/small corpora. For larger collections or multi-user production systems, consider Elasticsearch or OpenSearch.
- Use `-layout` with `pdftotext` only when you need to preserve column/line layout; it may introduce extra whitespace.
- Preprocess extracted text to normalize whitespace, remove repeated headers/footers, and extract visible page numbers from headers or footers if your documents store them.
- If you have many scanned images, OCR with a language model (`-l eng` or `eng+fra`) and consider running OCR asynchronously or in batches to avoid blocking the web server.

---

## Troubleshooting

- pdftotext not found: ensure Poppler binary is in PATH or configured in your ini/config.
- Poor OCR results: increase DPI when rendering page images (e.g., 300–600), and pass the correct Tesseract language models.
- Whoosh index is corrupted: rebuild the index by deleting the index directory and re-indexing.
- Memory/cpu: batch indexing and avoid running OCR during user requests — index offline.

---

## Example workflow (recommended)

1. Put PDFs in `pdfs/`.
2. Run an offline indexer script that:
   - iterates files
   - extracts per-page text with PyMuPDF
   - runs OCR for image-only pages
   - extracts metadata (title/author/year)
   - writes Whoosh documents (one document per page or per file)
3. Start Flask server to search and serve documents.

---

## License

Choose a license for your project (e.g., MIT). Add a `LICENSE` file to the repository.

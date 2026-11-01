"""
extract_text.py
Layer 3 — Deterministic text extraction from PDF or DOCX resume files.

Usage:
    python execution/extract_text.py <file_path_or_url>

Output (stdout JSON):
    {
        "text": "...",
        "method": "pdfplumber|ocr|docx",
        "word_count": 412,
        "is_scanned": false,
        "error": null
    }
"""

import sys
import json
import os
import re
import tempfile
import urllib.request
from pathlib import Path


# ── PDF extraction ────────────────────────────────────────────────────────────

def _words_to_text(word_list) -> str:
    """Group words into lines by vertical position, left-to-right within a line."""
    if not word_list:
        return ""
    sorted_words = sorted(word_list, key=lambda w: (round(float(w["top"]) / 5) * 5, float(w["x0"])))
    lines, current_line, current_top = [], [], None
    for w in sorted_words:
        top = round(float(w["top"]) / 5) * 5
        if current_top is None or abs(top - current_top) > 5:
            if current_line:
                lines.append(" ".join(current_line))
            current_line = [w["text"]]
            current_top = top
        else:
            current_line.append(w["text"])
    if current_line:
        lines.append(" ".join(current_line))
    return "\n".join(lines)


def _find_column_gutter(words, page_width: float, page_height: float):
    """
    Detect a 2-column layout by looking for an empty vertical band (>= 12pt wide,
    in the middle half of the page) that no body word touches. Words crossing it
    are allowed only in a full-width header at the top 25% of the page.
    Returns (gutter_x, header_bottom) or None for single-column pages.
    """
    half_band = 6
    best = None
    for gx in range(int(page_width * 0.25), int(page_width * 0.75), 2):
        crossing = [w for w in words
                    if float(w["x0"]) < gx + half_band and float(w["x1"]) > gx - half_band]
        if any(float(w["top"]) > page_height * 0.25 for w in crossing):
            continue
        header_bottom = max((float(w["bottom"]) for w in crossing), default=0.0)
        body = [w for w in words if float(w["top"]) > header_bottom]
        left = [w for w in body if float(w["x1"]) <= gx]
        right = [w for w in body if float(w["x1"]) > gx]
        if min(len(left), len(right)) < 0.15 * max(len(body), 1):
            continue
        # Anything above the point where both columns have started is header (e.g. a name
        # sitting over one column only)
        columns_start = max(min(float(w["top"]) for w in left), min(float(w["top"]) for w in right))
        header_bottom = max(header_bottom, columns_start - 1)
        if best is None or header_bottom < best[1]:
            best = (gx, header_bottom)
    return best


def _extract_pdf_pdfplumber(path: str) -> tuple[str, bool]:
    """
    Attempts to extract text from a digital PDF using pdfplumber.
    Handles 2-column layouts: if a clear vertical gutter is found, the header is
    emitted first, then the left column, then the right column.
    Returns (text, is_scanned).
    """
    import pdfplumber

    pages_text = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            words = page.extract_words(x_tolerance=3, y_tolerance=3)
            if not words:
                pages_text.append("")
                continue

            gutter = _find_column_gutter(words, float(page.width), float(page.height))
            if gutter:
                gx, header_bottom = gutter
                header = [w for w in words if float(w["top"]) <= header_bottom]
                body = [w for w in words if float(w["top"]) > header_bottom]
                parts = [
                    _words_to_text(header),
                    _words_to_text([w for w in body if float(w["x1"]) <= gx]),
                    _words_to_text([w for w in body if float(w["x1"]) > gx]),
                ]
                page_text = "\n".join(p for p in parts if p)
            else:
                page_text = _words_to_text(words)

            pages_text.append(page_text)

    full_text = "\n\n".join(pages_text).strip()
    word_count = len(full_text.split())
    is_scanned = word_count < 30  # digital PDFs, even short fresher resumes, have far more
    return full_text, is_scanned


def _extract_pdf_ocr(path: str) -> str:
    """
    Fallback: OCR using pytesseract on each page rendered as an image.
    Requires: pytesseract + tesseract binary, pdf2image + poppler.
    """
    import pytesseract
    from pdf2image import convert_from_path

    pages = convert_from_path(path, dpi=200)
    texts = []
    for page_img in pages:
        texts.append(pytesseract.image_to_string(page_img, lang="eng"))
    return "\n\n".join(texts).strip()


def extract_pdf(path: str) -> dict:
    try:
        text, is_scanned = _extract_pdf_pdfplumber(path)
    except Exception as e:
        return {"text": "", "method": "pdfplumber", "word_count": 0,
                "is_scanned": True, "error": f"pdfplumber failed: {e}"}

    if is_scanned:
        try:
            text = _extract_pdf_ocr(path)
            return {"text": text, "method": "ocr",
                    "word_count": len(text.split()), "is_scanned": True, "error": None}
        except Exception as e:
            return {"text": text, "method": "pdfplumber_fallback",
                    "word_count": len(text.split()), "is_scanned": True,
                    "error": f"OCR unavailable: {e}"}

    return {"text": text, "method": "pdfplumber",
            "word_count": len(text.split()), "is_scanned": False, "error": None}


# ── DOCX extraction ───────────────────────────────────────────────────────────

def extract_docx(path: str) -> dict:
    """
    Extract text from DOCX via python-docx.
    Reads both paragraphs and table cells (flattened to key: value style).
    """
    try:
        from docx import Document
        from docx.oxml.ns import qn
        from docx.table import Table
        from docx.text.paragraph import Paragraph
    except ImportError:
        return {"text": "", "method": "docx", "word_count": 0,
                "is_scanned": False, "error": "python-docx not installed"}

    try:
        doc = Document(path)
        parts = []

        # Walk the body in document order so tables stay inside their section
        for child in doc.element.body.iterchildren():
            if child.tag == qn("w:p"):
                line = Paragraph(child, doc).text.strip()
                if line:
                    parts.append(line)
            elif child.tag == qn("w:tbl"):
                for row in Table(child, doc).rows:
                    cells = [c.text.strip() for c in row.cells if c.text.strip()]
                    if cells:
                        parts.append(" | ".join(cells))

        text = "\n".join(parts)
        return {"text": text, "method": "docx",
                "word_count": len(text.split()), "is_scanned": False, "error": None}
    except Exception as e:
        return {"text": "", "method": "docx", "word_count": 0,
                "is_scanned": False, "error": str(e)}


# ── URL download ──────────────────────────────────────────────────────────────

def download_file(url: str, dest_dir: str) -> str:
    """Download file from URL; preserve extension. Returns local path."""
    # Detect extension from URL
    url_path = url.split("?")[0]
    ext = Path(url_path).suffix.lower()
    if ext not in (".pdf", ".docx"):
        ext = ".pdf"  # default assumption

    dest = os.path.join(dest_dir, f"resume{ext}")
    urllib.request.urlretrieve(url, dest)

    # URL extensions lie (or are missing) — trust the file's magic bytes
    with open(dest, "rb") as f:
        magic = f.read(4)
    sniffed = ".docx" if magic.startswith(b"PK") else ".pdf" if magic.startswith(b"%PDF") else ext
    if sniffed != ext:
        new_dest = os.path.join(dest_dir, f"resume{sniffed}")
        os.rename(dest, new_dest)
        dest = new_dest
    return dest


# ── Main entrypoint ───────────────────────────────────────────────────────────

def extract_text(source: str) -> dict:
    """
    Accept a file path or URL. Returns extraction result dict.
    """
    with tempfile.TemporaryDirectory() as tmp:
        # Download if URL
        if source.startswith("http://") or source.startswith("https://"):
            try:
                local_path = download_file(source, tmp)
            except Exception as e:
                return {"text": "", "method": "download", "word_count": 0,
                        "is_scanned": False, "error": f"Download failed: {e}"}
        else:
            local_path = source

        ext = Path(local_path).suffix.lower()
        if ext == ".pdf":
            return extract_pdf(local_path)
        elif ext == ".docx":
            return extract_docx(local_path)
        else:
            return {"text": "", "method": "unknown", "word_count": 0,
                    "is_scanned": False, "error": f"Unsupported file type: {ext}"}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: python extract_text.py <file_path_or_url>"}))
        sys.exit(1)

    result = extract_text(sys.argv[1])
    print(json.dumps(result, indent=2, ensure_ascii=False))

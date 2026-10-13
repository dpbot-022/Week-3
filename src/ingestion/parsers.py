import re
import fitz  # PyMuPDF
from typing import Dict, Any, Tuple, List
from pathlib import Path

class DocumentParser:
    """Parses plain text, markdown, and PDFs with precise page-level metadata."""

    @staticmethod
    def parse_pdf(file_bytes: bytes, filename: str = "document.pdf") -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Extracts text from PDF bytes page by page with page numbers and span offsets."""
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        pages: List[Dict[str, Any]] = []
        total_chars = 0

        for page_idx in range(len(doc)):
            page = doc[page_idx]
            page_text = page.get_text("text")
            cleaned_page = DocumentParser._clean_whitespace(page_text)
            if cleaned_page:
                pages.append({
                    "page_number": page_idx + 1,
                    "text": cleaned_page,
                    "char_start": total_chars,
                    "char_end": total_chars + len(cleaned_page)
                })
                total_chars += len(cleaned_page) + 1

        meta = {
            "source": filename,
            "file_type": ".pdf",
            "page_count": len(doc),
            "total_chars": total_chars,
            "format": "pdf"
        }
        return pages, meta

    @staticmethod
    def parse_text(raw_text: str, filename: str = "document.txt") -> Tuple[str, Dict[str, Any]]:
        meta: Dict[str, Any] = {
            "source": filename,
            "file_type": Path(filename).suffix.lower() or ".txt",
            "raw_length": len(raw_text),
        }
        
        if "# " in raw_text or "```" in raw_text or "|---" in raw_text:
            meta["format"] = "markdown"
            headers = re.findall(r"(?:^|\n)#{1,6}\s+(.+)", raw_text)
            if headers:
                meta["detected_headers"] = headers[:10]
        else:
            meta["format"] = "plain_text"

        cleaned_text = DocumentParser._clean_whitespace(raw_text)
        return cleaned_text, meta

    @staticmethod
    def _clean_whitespace(text: str) -> str:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

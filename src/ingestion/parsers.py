import re
from typing import Dict, Any, Tuple
from pathlib import Path

class DocumentParser:
    """Parses various document types (text, markdown, code, and structured formats)."""
    @staticmethod
    def parse_text(raw_text: str, filename: str = "document.txt") -> Tuple[str, Dict[str, Any]]:
        meta: Dict[str, Any] = {
            "source": filename,
            "file_type": Path(filename).suffix.lower() or ".txt",
            "raw_length": len(raw_text),
        }
        
        # Detect if markdown
        if "# " in raw_text or "```" in raw_text or "|---" in raw_text:
            meta["format"] = "markdown"
            # Extract headers for structure metadata
            headers = re.findall(r"(?:^|\n)#{1,6}\s+(.+)", raw_text)
            if headers:
                meta["detected_headers"] = headers[:10]
        else:
            meta["format"] = "plain_text"

        cleaned_text = DocumentParser._clean_whitespace(raw_text)
        return cleaned_text, meta

    @staticmethod
    def _clean_whitespace(text: str) -> str:
        # Standardize newlines, collapse 3+ newlines to 2
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

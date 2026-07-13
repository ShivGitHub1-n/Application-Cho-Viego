from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import re
import zlib
from zipfile import BadZipFile


class ResumeExtractionError(ValueError):
    pass


class UnsupportedResumeFileError(ResumeExtractionError):
    pass


class EmptyResumeFileError(ResumeExtractionError):
    pass


class ImageOnlyResumeError(ResumeExtractionError):
    pass


@dataclass(frozen=True)
class ExtractedResumeText:
    filename: str
    source_format: str
    text: str


def extract_resume_text(filename: str, content: bytes) -> ExtractedResumeText:
    suffix = Path(filename).suffix.casefold()
    if suffix not in {".docx", ".pdf"}:
        raise UnsupportedResumeFileError("Only .docx and text-based .pdf files are supported.")
    if not content:
        raise EmptyResumeFileError("The uploaded resume file is empty.")
    if suffix == ".docx":
        text = _extract_docx(content)
        source_format = "docx"
    else:
        text = _extract_pdf(content)
        source_format = "pdf"
    normalized = "\n".join(line.rstrip() for line in text.replace("\r\n", "\n").split("\n")).strip()
    if not normalized:
        raise ImageOnlyResumeError(
            "No selectable text was found. Image-only resumes require OCR, which is not enabled."
        )
    return ExtractedResumeText(filename=filename, source_format=source_format, text=normalized)


def _extract_docx(content: bytes) -> str:
    try:
        from docx import Document

        document = Document(BytesIO(content))
        parts = [paragraph.text for paragraph in document.paragraphs]
        for table in document.tables:
            parts.extend("\t".join(cell.text for cell in row.cells) for row in table.rows)
        return "\n".join(parts)
    except (BadZipFile, ValueError, OSError) as error:
        raise ResumeExtractionError("The DOCX file is corrupt or unreadable.") from error
    except Exception as error:
        raise ResumeExtractionError("The DOCX file could not be read.") from error


def _extract_pdf(content: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        try:
            from PyPDF2 import PdfReader
        except ImportError as error:
            return _extract_pdf_text_fallback(content)
    try:
        reader = PdfReader(BytesIO(content))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as error:
        raise ResumeExtractionError("The PDF file is corrupt or unreadable.") from error


def _extract_pdf_text_fallback(content: bytes) -> str:
    """Extract common literal-string PDF text operators when no PDF library is installed."""

    try:
        source = content.decode("latin-1")
    except UnicodeDecodeError as error:
        raise ResumeExtractionError("The PDF encoding could not be read.") from error
    if not source.startswith("%PDF-"):
        raise ResumeExtractionError("The PDF file is corrupt or unreadable.")
    compressed_text = []
    for match in re.finditer(
        rb"<<(?P<dictionary>.*?)>>\s*stream\r?\n(?P<data>.*?)\r?\nendstream",
        content,
        re.DOTALL,
    ):
        if b"/FlateDecode" not in match.group("dictionary"):
            continue
        try:
            compressed_text.append(zlib.decompress(match.group("data")).decode("latin-1"))
        except (zlib.error, UnicodeDecodeError):
            continue
    source = "\n".join([source, *compressed_text])
    strings = re.findall(r"\(((?:[^\\()]|\\.)*)\)\s*T[Jj]", source)
    decoded = []
    for value in strings:
        decoded.append(
            value.replace(r"\(", "(").replace(r"\)", ")").replace(r"\\", "\\")
        )
    return "\n".join(decoded)

from io import BytesIO

import pytest
from docx import Document

from resume_tailor.infrastructure.resume_extraction import (
    EmptyResumeFileError,
    ImageOnlyResumeError,
    ResumeExtractionError,
    UnsupportedResumeFileError,
    extract_resume_text,
)


def _docx_bytes() -> bytes:
    document = Document()
    document.add_paragraph("Jane Candidate")
    document.add_paragraph("Engineer | Toronto")
    output = BytesIO()
    document.save(output)
    return output.getvalue()


def _pdf_bytes(text: str) -> bytes:
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    output = BytesIO()
    output.write(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(output.tell())
        output.write(f"{index} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = output.tell()
    output.write(f"xref\n0 {len(objects) + 1}\n".encode())
    output.write(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.write(f"{offset:010d} 00000 n \n".encode())
    output.write(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    )
    return output.getvalue()


def test_docx_text_extraction() -> None:
    result = extract_resume_text("resume.docx", _docx_bytes())
    assert result.source_format == "docx"
    assert "Jane Candidate" in result.text
    assert "Engineer | Toronto" in result.text


def test_text_pdf_extraction() -> None:
    result = extract_resume_text("resume.pdf", _pdf_bytes("Jane Candidate"))
    assert result.source_format == "pdf"
    assert "Jane Candidate" in result.text


def test_unsupported_corrupt_empty_and_image_only_files_are_clear() -> None:
    with pytest.raises(UnsupportedResumeFileError):
        extract_resume_text("resume.txt", b"text")
    with pytest.raises(EmptyResumeFileError):
        extract_resume_text("resume.docx", b"")
    with pytest.raises(ResumeExtractionError):
        extract_resume_text("resume.docx", b"not-a-docx")
    with pytest.raises(ImageOnlyResumeError):
        extract_resume_text("resume.pdf", _pdf_bytes(""))

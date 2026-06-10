from io import BytesIO

import pytest

from app.services.document_parser import (
    DocxDocument,
    DocumentParseError,
    extract_text_from_upload,
)
from app.services.rag_service import RagValidationError, rag_service


def test_extract_txt_text():
    text = extract_text_from_upload("notes.txt", "hello txt".encode("utf-8"))

    assert text == "hello txt"


def test_extract_markdown_text():
    text = extract_text_from_upload("notes.md", "# Title\n\nbody".encode("utf-8"))

    assert "# Title" in text
    assert "body" in text


def test_unsupported_file_type_has_clear_error():
    with pytest.raises(DocumentParseError, match="当前仅支持 TXT、Markdown、PDF、DOCX 文件"):
        extract_text_from_upload("data.xlsx", b"content")


def test_empty_upload_rejected_before_embedding():
    with pytest.raises(RagValidationError, match="上传文件不能为空"):
        rag_service.create_document(None, "empty.txt", b"")


def test_docx_text_extraction_when_dependency_available():
    if DocxDocument is None:
        pytest.skip("python-docx is not installed")

    buffer = BytesIO()
    document = DocxDocument()
    document.add_paragraph("docx paragraph")
    document.save(buffer)

    text = extract_text_from_upload("sample.docx", buffer.getvalue())

    assert "docx paragraph" in text

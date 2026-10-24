import csv
import hashlib
import io
import json
import re
from pathlib import PurePath

from bs4 import BeautifulSoup
from pypdf import PdfReader

from casefile.models import Document

DOCUMENT_ID_LENGTH = 16


class UnsupportedFormat(ValueError):
    pass


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def create_document_id(source_name: str) -> str:
    """Stable id from the source name, so re-uploading the same file means 'update'."""
    return hashlib.sha1(source_name.encode("utf-8")).hexdigest()[:DOCUMENT_ID_LENGTH]


def clean_whitespace(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def build_document(source_name: str, title: str, text: str, **metadata) -> Document:
    text = clean_whitespace(text)
    return Document(
        doc_id=create_document_id(source_name),
        title=title,
        text=text,
        content_hash=hash_text(text),
        metadata={"source": source_name, **metadata},
    )


def load_pdf_file(file_name: str, file_bytes: bytes) -> list[Document]:
    reader = PdfReader(io.BytesIO(file_bytes))
    page_texts = [(page.extract_text() or "") for page in reader.pages]
    title = (reader.metadata.title if reader.metadata else None) or file_name
    # Keep page markers in the text so a citation can say where the fact was found.
    text = "\n\n".join(
        f"[page {page_number}]\n{page_text}"
        for page_number, page_text in enumerate(page_texts, start=1)
        if page_text.strip()
    )
    return [build_document(file_name, title, text, format="pdf", pages=len(page_texts))]


def load_text_file(file_name: str, file_bytes: bytes) -> list[Document]:
    file_format = PurePath(file_name).suffix.lstrip(".").lower()
    text = file_bytes.decode("utf-8", errors="replace")
    return [build_document(file_name, file_name, text, format=file_format)]


def load_html_file(file_name: str, file_bytes: bytes) -> list[Document]:
    soup = BeautifulSoup(file_bytes, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    has_title = soup.title and soup.title.string
    title = soup.title.string.strip() if has_title else file_name
    return [build_document(file_name, title, soup.get_text("\n"), format="html")]


def convert_record_to_document(file_name: str, record_number: int, record: dict) -> Document:
    """JSON record -> Document. Accepts {id,title,text} and a few common aliases."""
    text = record.get("text") or record.get("content") or record.get("body") or ""
    if isinstance(text, list):  # HotpotQA stores a paragraph as a list of sentences
        text = " ".join(text)
    title = str(record.get("title") or f"{file_name}#{record_number}")
    record_id = record.get("id", record_number)
    return build_document(f"{file_name}#{record_id}", title, str(text), format="json", record=record_id)


def load_json_file(file_name: str, file_bytes: bytes) -> list[Document]:
    parsed = json.loads(file_bytes.decode("utf-8"))
    records = parsed if isinstance(parsed, list) else [parsed]
    return [
        convert_record_to_document(file_name, record_number, record)
        for record_number, record in enumerate(records)
        if isinstance(record, dict)
    ]


def load_jsonl_file(file_name: str, file_bytes: bytes) -> list[Document]:
    lines = file_bytes.decode("utf-8").splitlines()
    return [
        convert_record_to_document(file_name, line_number, json.loads(line))
        for line_number, line in enumerate(lines)
        if line.strip()
    ]


def load_csv_file(file_name: str, file_bytes: bytes) -> list[Document]:
    rows = csv.DictReader(io.StringIO(file_bytes.decode("utf-8", errors="replace")))
    documents = []
    for row_number, row in enumerate(rows):
        text = "; ".join(f"{column}: {value}" for column, value in row.items() if value)
        if text:
            documents.append(build_document(f"{file_name}#{row_number}", f"{file_name} row {row_number}",
                                            text, format="csv", row=row_number))
    return documents


LOADERS_BY_EXTENSION = {
    ".pdf": load_pdf_file,
    ".txt": load_text_file,
    ".md": load_text_file,
    ".html": load_html_file,
    ".htm": load_html_file,
    ".json": load_json_file,
    ".jsonl": load_jsonl_file,
    ".csv": load_csv_file,
}
SUPPORTED_EXTENSIONS = sorted(LOADERS_BY_EXTENSION)


def load_documents(file_name: str, file_bytes: bytes) -> list[Document]:
    """Turn an uploaded file into one or more Documents. Raises UnsupportedFormat / ValueError."""
    extension = PurePath(file_name).suffix.lower()
    load_file = LOADERS_BY_EXTENSION.get(extension)
    if load_file is None:
        raise UnsupportedFormat(f"Unsupported file type '{extension}'. Supported: {SUPPORTED_EXTENSIONS}")
    documents = [document for document in load_file(PurePath(file_name).name, file_bytes) if document.text]
    if not documents:
        raise ValueError(f"No text could be extracted from '{file_name}'")
    return documents

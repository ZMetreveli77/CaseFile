import csv
import hashlib
import io
import json
import re
from pathlib import PurePath

from bs4 import BeautifulSoup
from pypdf import PdfReader

from casefile.models import Document

SUPPORTED = {".pdf", ".txt", ".md", ".html", ".htm", ".json", ".jsonl", ".csv"}


class UnsupportedFormat(ValueError):
    pass


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _doc_id(source: str) -> str:
    """Stable id from the source name, so re-uploading the same file means 'update'."""
    return hashlib.sha1(source.encode("utf-8")).hexdigest()[:16]


def _clean(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _make(source: str, title: str, text: str, **meta) -> Document:
    text = _clean(text)
    return Document(
        doc_id=_doc_id(source),
        title=title,
        text=text,
        content_hash=_hash(text),
        metadata={"source": source, **meta},
    )


def _load_pdf(name: str, data: bytes) -> list[Document]:
    reader = PdfReader(io.BytesIO(data))
    pages = [(page.extract_text() or "") for page in reader.pages]
    title = (reader.metadata.title if reader.metadata else None) or name
    # Keep page markers in the text so a citation can say where the fact was found.
    text = "\n\n".join(f"[page {i + 1}]\n{p}" for i, p in enumerate(pages) if p.strip())
    return [_make(name, title, text, format="pdf", pages=len(pages))]


def _load_text(name: str, data: bytes) -> list[Document]:
    fmt = PurePath(name).suffix.lstrip(".").lower()
    return [_make(name, name, data.decode("utf-8", errors="replace"), format=fmt)]


def _load_html(name: str, data: bytes) -> list[Document]:
    soup = BeautifulSoup(data, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    title = soup.title.string.strip() if soup.title and soup.title.string else name
    return [_make(name, title, soup.get_text("\n"), format="html")]


def _record_to_doc(name: str, i: int, rec: dict) -> Document:
    """JSON record -> Document. Accepts {id,title,text} and a few common aliases."""
    text = rec.get("text") or rec.get("content") or rec.get("body") or ""
    if isinstance(text, list):  # HotpotQA stores a paragraph as a list of sentences
        text = " ".join(text)
    title = str(rec.get("title") or f"{name}#{i}")
    rec_id = rec.get("id", i)
    return _make(f"{name}#{rec_id}", title, str(text), format="json", record=rec_id)


def _load_json(name: str, data: bytes) -> list[Document]:
    parsed = json.loads(data.decode("utf-8"))
    records = parsed if isinstance(parsed, list) else [parsed]
    return [_record_to_doc(name, i, r) for i, r in enumerate(records) if isinstance(r, dict)]


def _load_jsonl(name: str, data: bytes) -> list[Document]:
    lines = data.decode("utf-8").splitlines()
    return [_record_to_doc(name, i, json.loads(line)) for i, line in enumerate(lines) if line.strip()]


def _load_csv(name: str, data: bytes) -> list[Document]:
    rows = csv.DictReader(io.StringIO(data.decode("utf-8", errors="replace")))
    docs = []
    for i, row in enumerate(rows):
        text = "; ".join(f"{k}: {v}" for k, v in row.items() if v)
        if text:
            docs.append(_make(f"{name}#{i}", f"{name} row {i}", text, format="csv", row=i))
    return docs


_LOADERS = {
    ".pdf": _load_pdf,
    ".txt": _load_text,
    ".md": _load_text,
    ".html": _load_html,
    ".htm": _load_html,
    ".json": _load_json,
    ".jsonl": _load_jsonl,
    ".csv": _load_csv,
}


def load_documents(filename: str, data: bytes) -> list[Document]:
    """Turn an uploaded file into one or more Documents. Raises UnsupportedFormat / ValueError."""
    ext = PurePath(filename).suffix.lower()
    loader = _LOADERS.get(ext)
    if loader is None:
        raise UnsupportedFormat(f"Unsupported file type '{ext}'. Supported: {sorted(SUPPORTED)}")
    docs = [d for d in loader(PurePath(filename).name, data) if d.text]
    if not docs:
        raise ValueError(f"No text could be extracted from '{filename}'")
    return docs

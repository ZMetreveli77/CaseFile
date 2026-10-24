import json

import pytest

from casefile.ingestion.loaders import UnsupportedFormat, load_documents


def make_pdf(page_texts: list[str]) -> bytes:
    """Build a minimal valid PDF with one line of text per page."""
    pdf_objects = ["<< /Type /Catalog /Pages 2 0 R >>", ""]
    page_references = []
    for page_text in page_texts:
        content = f"BT /F1 12 Tf 72 720 Td ({page_text}) Tj ET".encode()
        page_object_id, content_object_id = len(pdf_objects) + 1, len(pdf_objects) + 2
        page_references.append(f"{page_object_id} 0 R")
        pdf_objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {content_object_id} 0 R "
            f"/Resources << /Font << /F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> >> >> >>")
        pdf_objects.append(f"<< /Length {len(content)} >>\nstream\n{content.decode()}\nendstream")
    pdf_objects[1] = f"<< /Type /Pages /Kids [{' '.join(page_references)}] /Count {len(page_references)} >>"

    pdf_bytes, object_offsets = bytearray(b"%PDF-1.4\n"), []
    for object_number, pdf_object in enumerate(pdf_objects, start=1):
        object_offsets.append(len(pdf_bytes))
        pdf_bytes += f"{object_number} 0 obj\n{pdf_object}\nendobj\n".encode()
    cross_reference_offset = len(pdf_bytes)
    pdf_bytes += f"xref\n0 {len(pdf_objects) + 1}\n0000000000 65535 f \n".encode()
    pdf_bytes += "".join(f"{offset:010d} 00000 n \n" for offset in object_offsets).encode()
    pdf_bytes += (f"trailer\n<< /Size {len(pdf_objects) + 1} /Root 1 0 R >>\n"
                  f"startxref\n{cross_reference_offset}\n%%EOF").encode()
    return bytes(pdf_bytes)


def test_pdf_keeps_page_markers():
    [document] = load_documents("report.pdf", make_pdf(["Payments failed in March.", "Service B was affected."]))
    assert document.metadata["format"] == "pdf" and document.metadata["pages"] == 2
    assert "[page 1]" in document.text and "[page 2]" in document.text
    assert "Service B was affected." in document.text


def test_txt_and_md():
    [document] = load_documents("notes.md", b"# Title\n\nSome    text.\n\n\n\nMore.")
    assert document.metadata["format"] == "md"
    assert "Some text." in document.text and "\n\n\n" not in document.text


def test_html_strips_scripts():
    html = b"<html><head><title>Incident</title><script>var x=1;</script></head><body><p>Outage</p></body></html>"
    [document] = load_documents("page.html", html)
    assert document.title == "Incident" and "Outage" in document.text and "var x" not in document.text


def test_jsonl_hotpotqa_style_records():
    records = [{"id": "p1", "title": "Paris", "text": ["Paris is in France.", " It is big."]},
               {"id": "p2", "title": "Rome", "text": "Rome is in Italy."}]
    documents = load_documents("corpus.jsonl", "\n".join(json.dumps(record) for record in records).encode())
    assert [document.title for document in documents] == ["Paris", "Rome"]
    assert documents[0].text.startswith("Paris is in France.")
    assert documents[0].doc_id != documents[1].doc_id


def test_json_list_and_csv():
    json_documents = load_documents("data.json", json.dumps([{"title": "A", "content": "alpha"}]).encode())
    assert json_documents[0].text == "alpha"
    csv_documents = load_documents("t.csv", b"service,status\napi,down\ndb,ok\n")
    assert len(csv_documents) == 2 and csv_documents[0].text == "service: api; status: down"


def test_same_name_same_id_and_hash_tracks_content():
    first_version = load_documents("x.txt", b"version one")[0]
    second_version = load_documents("x.txt", b"version two")[0]
    assert first_version.doc_id == second_version.doc_id
    assert first_version.content_hash != second_version.content_hash


def test_unsupported_and_empty():
    with pytest.raises(UnsupportedFormat):
        load_documents("image.png", b"...")
    with pytest.raises(ValueError):
        load_documents("empty.txt", b"   ")

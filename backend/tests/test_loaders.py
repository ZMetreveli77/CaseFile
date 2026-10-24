import json

import pytest

from casefile.ingestion.loaders import UnsupportedFormat, load_documents


def make_pdf(pages: list[str]) -> bytes:
    """Build a minimal valid PDF with one line of text per page."""
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", ""]
    kids = []
    for text in pages:
        content = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
        page_id, content_id = len(objs) + 1, len(objs) + 2
        kids.append(f"{page_id} 0 R")
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {content_id} 0 R "
                    f"/Resources << /Font << /F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> >> >> >>")
        objs.append(f"<< /Length {len(content)} >>\nstream\n{content.decode()}\nendstream")
    objs[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>"

    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for i, obj in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{obj}\nendobj\n".encode()
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += "".join(f"{o:010d} 00000 n \n" for o in offsets).encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    return bytes(out)


def test_pdf_keeps_page_markers():
    [doc] = load_documents("report.pdf", make_pdf(["Payments failed in March.", "Service B was affected."]))
    assert doc.metadata["format"] == "pdf" and doc.metadata["pages"] == 2
    assert "[page 1]" in doc.text and "[page 2]" in doc.text
    assert "Service B was affected." in doc.text


def test_txt_and_md():
    [doc] = load_documents("notes.md", b"# Title\n\nSome    text.\n\n\n\nMore.")
    assert doc.metadata["format"] == "md"
    assert "Some text." in doc.text and "\n\n\n" not in doc.text


def test_html_strips_scripts():
    html = b"<html><head><title>Incident</title><script>var x=1;</script></head><body><p>Outage</p></body></html>"
    [doc] = load_documents("page.html", html)
    assert doc.title == "Incident" and "Outage" in doc.text and "var x" not in doc.text


def test_jsonl_hotpotqa_style_records():
    lines = [{"id": "p1", "title": "Paris", "text": ["Paris is in France.", " It is big."]},
             {"id": "p2", "title": "Rome", "text": "Rome is in Italy."}]
    docs = load_documents("corpus.jsonl", "\n".join(json.dumps(x) for x in lines).encode())
    assert [d.title for d in docs] == ["Paris", "Rome"]
    assert docs[0].text.startswith("Paris is in France.")
    assert docs[0].doc_id != docs[1].doc_id


def test_json_list_and_csv():
    docs = load_documents("data.json", json.dumps([{"title": "A", "content": "alpha"}]).encode())
    assert docs[0].text == "alpha"
    rows = load_documents("t.csv", b"service,status\napi,down\ndb,ok\n")
    assert len(rows) == 2 and rows[0].text == "service: api; status: down"


def test_same_name_same_id_and_hash_tracks_content():
    a = load_documents("x.txt", b"version one")[0]
    b = load_documents("x.txt", b"version two")[0]
    assert a.doc_id == b.doc_id and a.content_hash != b.content_hash


def test_unsupported_and_empty():
    with pytest.raises(UnsupportedFormat):
        load_documents("image.png", b"...")
    with pytest.raises(ValueError):
        load_documents("empty.txt", b"   ")

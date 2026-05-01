from pathlib import Path

from backend.app.docs.loader import page_for_offset, pdf_to_markdown

FIXTURE = Path(__file__).parent / "fixtures" / "sample.pdf"


def test_loader_extracts_text_and_pages() -> None:
    md, ranges = pdf_to_markdown(FIXTURE.read_bytes())
    assert "Visa Chargebacks" in md
    assert "Returns Policy" in md
    assert len(ranges) == 2
    assert {r.page_number for r in ranges} == {1, 2}
    assert ranges[0].start_offset == 0
    # offsets must be monotonically non-decreasing and end-aligned
    for prev, nxt in zip(ranges, ranges[1:], strict=False):
        assert prev.end_offset <= nxt.start_offset
    assert ranges[-1].end_offset <= len(md)


def test_page_for_offset() -> None:
    md, ranges = pdf_to_markdown(FIXTURE.read_bytes())
    chargebacks_at = md.find("Visa Chargebacks")
    returns_at = md.find("Returns Policy")
    assert chargebacks_at != -1
    assert returns_at != -1
    assert page_for_offset(ranges, chargebacks_at) == 1
    assert page_for_offset(ranges, returns_at) == 2
    assert page_for_offset(ranges, len(md) + 1) is None

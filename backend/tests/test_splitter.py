from backend.app.config import settings
from backend.app.docs.loader import PageRange
from backend.app.docs.splitter import split

SAMPLE = """\
# Visa Chargebacks

## Reason 4853

Cardholder dispute. Time limit 120 days. This applies across all regions.

## Reason 4837

No cardholder authorization. Same time limit applies.

# Returns

## Domestic returns

Returns are accepted within 30 days of purchase. Items must be unworn.
"""


def test_split_assigns_heading_paths() -> None:
    chunks = split(SAMPLE, [])
    assert len(chunks) == 3        # one per leaf section with body text
    headings = {c.heading for c in chunks}
    assert {"Reason 4853", "Reason 4837", "Domestic returns"} == headings


def test_split_respects_chunk_size() -> None:
    long_section = "lorem ipsum " * 5000  # ~60 000 chars
    md = "# Big section\n\n" + long_section
    chunks = split(md, [])
    char_limit = settings.docs_chunk_size * 4
    for c in chunks:
        # langchain may slightly overshoot at boundaries; allow modest slack
        assert len(c.text) <= char_limit + 200


def test_split_stamps_pages_via_offset_map() -> None:
    chunks = split(SAMPLE, [
        PageRange(start_offset=0, end_offset=SAMPLE.find("# Returns"), page_number=1),
        PageRange(start_offset=SAMPLE.find("# Returns"), end_offset=len(SAMPLE), page_number=2),
    ])
    assert chunks
    page1_chunks = [c for c in chunks if c.page == 1]
    page2_chunks = [c for c in chunks if c.page == 2]
    assert page1_chunks and page2_chunks
    assert any(c.heading and "Reason" in c.heading for c in page1_chunks)
    assert any(c.heading == "Domestic returns" for c in page2_chunks)


def test_split_empty_input_returns_empty_list() -> None:
    assert split("", []) == []
    assert split("   \n\n   ", []) == []

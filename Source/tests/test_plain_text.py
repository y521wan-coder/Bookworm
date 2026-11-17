from blake3 import blake3

from bookworm.document.formats.plain_text import (
    PAGINATION_THRESHOLD_CHARS,
    TARGET_PAGE_CHARS,
    PlainTextDocument,
)
from bookworm.document.uri import DocumentUri


def make_large_plain_text():
    line = "凡人修仙传测试内容" * 8 + "\n"
    return line * ((PAGINATION_THRESHOLD_CHARS // len(line)) + 1000)


def test_large_plain_text_is_split_on_lines_without_losing_content(tmp_path):
    path = tmp_path / "large.txt"
    text = make_large_plain_text()
    path.write_text(text, encoding="utf-8")
    document = PlainTextDocument(DocumentUri.from_filename(path))

    document.read()

    assert not document.is_single_page_document()
    assert "".join(page.get_text() for page in document) == document.get_content()
    assert all(page.get_text().endswith("\n") for page in document)
    assert max(len(page.get_text()) for page in document) <= TARGET_PAGE_CHARS


def test_large_plain_text_converts_legacy_absolute_position(tmp_path):
    path = tmp_path / "large.txt"
    path.write_text(make_large_plain_text(), encoding="utf-8")
    document = PlainTextDocument(DocumentUri.from_filename(path))
    document.read()
    target_page = min(3, len(document) - 1)
    page_start = document._page_spans[target_page][0]

    assert document.normalize_stored_position(0, page_start + 17) == (target_page, 17)


def test_paginated_plain_text_keeps_single_page_content_hash(tmp_path):
    path = tmp_path / "large.txt"
    path.write_text(make_large_plain_text(), encoding="utf-8")
    document = PlainTextDocument(DocumentUri.from_filename(path))
    document.read()
    encoded_text = document.get_content().encode()
    expected_hasher = blake3()
    expected_hasher.update(len(encoded_text).to_bytes(8, "big"))
    expected_hasher.update(encoded_text)

    assert document.get_content_hash() == expected_hasher.hexdigest()

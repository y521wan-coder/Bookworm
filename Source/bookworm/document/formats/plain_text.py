# coding: utf-8

from __future__ import annotations

import os
from bisect import bisect_right
from functools import cached_property

import ftfy
from blake3 import blake3

from bookworm.logger import logger
from bookworm.structured_text import TextRange
from bookworm.utils import (
    TextContentDecoder,
    normalize_line_breaks,
    remove_excess_blank_lines,
)

from .. import BookMetadata
from .. import DocumentCapability as DC
from .. import BasePage, DocumentError, Pager, Section, SinglePageDocument

log = logger.getChild(__name__)
MAX_NUM_CHARS = round(2e6)
# Loading millions of characters into one native RichEdit control causes its
# accessibility and caret-notification paths to block the GUI thread.  Large
# text files are therefore exposed as reasonably sized logical pages.
PAGINATION_THRESHOLD_CHARS = 250_000
TARGET_PAGE_CHARS = 50_000


class PlainTextPage(BasePage):
    """A line-aligned window into a large plain-text document."""

    def get_text(self):
        return self.document.get_text_for_page(self.index)

    def get_storage_text(self):
        return self.get_text()

    def get_legacy_text(self):
        return self.get_text()


class PlainTextDocument(SinglePageDocument):
    """For plain text files"""

    format = "txt"
    # Translators: the name of a document file format
    name = _("Plain Text File")
    extensions = ("*.txt",)
    # Large text decoding must not run on wx's main thread.
    capabilities = DC.SINGLE_PAGE | DC.LINKS | DC.STRUCTURED_NAVIGATION | DC.ASYNC_READ

    def read(self):
        self.filename = self.get_file_system_path()
        with open(self.filename, "rb") as file:
            content = file.read()
        self.text = TextContentDecoder(content).get_utf8()
        self._page_spans = self._build_page_spans(self.get_content())
        super().read()

    @staticmethod
    def _build_page_spans(text):
        if len(text) <= PAGINATION_THRESHOLD_CHARS:
            return ((0, len(text)),)
        spans = []
        start = 0
        text_length = len(text)
        while start < text_length:
            target = min(start + TARGET_PAGE_CHARS, text_length)
            if target < text_length:
                stop = text.rfind("\n", start + 1, target + 1)
                if stop <= start:
                    stop = text.find("\n", target)
                if stop >= 0:
                    target = stop + 1
            spans.append((start, target))
            start = target
        return tuple(spans) or ((0, 0),)

    def __len__(self):
        return len(self._page_spans)

    def get_page(self, index):
        if index not in self:
            raise IndexError(index)
        return PlainTextPage(self, index)

    def get_text_for_page(self, index):
        start, stop = self._page_spans[index]
        return self.get_content()[start:stop]

    def is_single_page_document(self):
        return len(self) == 1

    def normalize_stored_position(self, page, position):
        """Convert positions saved by the former one-page text model."""
        if not self._page_spans:
            return 0, 0
        if 0 <= page < len(self):
            page_length = self._page_spans[page][1] - self._page_spans[page][0]
            if 0 <= position <= page_length:
                return page, position
        absolute_position = max(0, min(position, len(self.get_content())))
        page_starts = tuple(start for start, _stop in self._page_spans)
        target_page = max(0, bisect_right(page_starts, absolute_position) - 1)
        target_page = min(target_page, len(self) - 1)
        return target_page, absolute_position - self._page_spans[target_page][0]

    def get_content_hash(self):
        """Keep hashes compatible with the former single-page text model."""
        if hasattr(self, "_content_hash"):
            return self._content_hash
        text = self.get_content()
        if not self._has_hashable_text(text):
            self._content_hash = None
            return None
        encoded_text = text.encode()
        hasher = blake3()
        hasher.update(len(encoded_text).to_bytes(8, "big"))
        hasher.update(encoded_text)
        self._content_hash = hasher.hexdigest()
        self._content_hash_has_images = False
        return self._content_hash

    def get_content(self):
        if len(self.text) > MAX_NUM_CHARS:
            return self.text
        text = remove_excess_blank_lines(self.text)
        config = ftfy.TextFixerConfig(
            fix_character_width=False,
            uncurl_quotes=False,
            fix_latin_ligatures=False,
            normalization="NFC",
            unescape_html=False,
            fix_line_breaks=True,
            max_decode_length=MAX_NUM_CHARS,
        )
        return ftfy.fix_text(text, config)

    def close(self):
        super().close()
        del self.text
        del self._page_spans

    @cached_property
    def toc_tree(self):
        return Section(
            title="",
            pager=Pager(first=0, last=max(0, len(self) - 1)),
            text_range=TextRange(0, len(self.get_content())),
        )

    @cached_property
    def metadata(self):
        return BookMetadata(
            title=os.path.split(self.filename)[-1][:-4],
            author="",
            publication_year="",
        )

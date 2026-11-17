
"""Provides primitives for structuring a blob of text."""

from __future__ import annotations

import math
import operator
from collections.abc import Container
from functools import cached_property, partial

import attr
from pytqsm import segment as segment_sentences

from bookworm import typehints as t

TEXT_OBJECT_REPLACEMENT_CHAR = "\ufffc"
LEGACY_POSITION_MODEL_VERSION = 1
LEGACY_CONTENT_HASH_VERSION = 1
CURRENT_POSITION_MODEL_VERSION = 2
CURRENT_CONTENT_HASH_VERSION = 2


@attr.s(auto_attribs=True, slots=True, hash=False)
class TextRange(Container):
    """Represents a text range refering to a substring."""

    start: int
    stop: int

    def __hash__(self):
        return hash((self.start, self.stop))

    @property
    def midrange(self):
        return math.floor((self.start + self.stop) / 2)

    def operator_imp(self, other, operator_func):
        if isinstance(other, self.__class__):
            return operator_func(self.start, other.start)
        if type(other) is int:
            return operator_func(self.start, other)
        return NotImplemented

    def __gt__(self, other):
        return self.operator_imp(other, operator.gt)

    def __gte__(self, other):
        return self.operator_imp(other, operator.gte)

    def __lt__(self, other):
        return self.operator_imp(other, operator.lt)

    def __lte__(self, other):
        return self.operator_imp(other, operator.lte)

    def __contains__(self, pos):
        return self.start <= pos <= self.stop

    def __iter__(self):
        return iter((self.start, self.stop))

    def astuple(self):
        return (self.start, self.stop)

    def as_slice(self):
        return slice(self.start, self.stop)


@attr.s(auto_attribs=True, slots=True, frozen=True)
class TextPositionReplacement:
    display_start: int
    display_stop: int
    storage_start: int
    storage_stop: int

    @property
    def display_length(self):
        return self.display_stop - self.display_start

    @property
    def storage_length(self):
        return self.storage_stop - self.storage_start


class TextPositionMappingError(ValueError):
    """Raised when two text models cannot be mapped without guessing."""


@attr.s(auto_attribs=True, slots=True, frozen=True)
class TextPositionMap:
    """Maps user-visible text offsets to stable storage offsets."""

    display_length: int
    storage_length: int
    replacements: tuple[TextPositionReplacement, ...] = ()

    @classmethod
    def identity(cls, text_length=0):
        return cls(
            display_length=max(text_length, 0),
            storage_length=max(text_length, 0),
        )

    @classmethod
    def from_collapsed_ranges(cls, display_text, ranges, replacement_text=None):
        replacement_text = replacement_text or TEXT_OBJECT_REPLACEMENT_CHAR
        normalized_ranges = []
        previous_stop = 0
        for text_range in sorted(ranges, key=lambda rng: (rng.start, rng.stop)):
            start = max(0, text_range.start)
            stop = min(len(display_text), text_range.stop)
            if stop <= start or start < previous_stop:
                continue
            normalized_ranges.append(TextRange(start, stop))
            previous_stop = stop
        if not normalized_ranges:
            return display_text, cls.identity(len(display_text))

        storage_chunks = []
        replacements = []
        display_cursor = 0
        storage_cursor = 0
        for display_range in normalized_ranges:
            prefix = display_text[display_cursor : display_range.start]
            storage_chunks.append(prefix)
            storage_cursor += len(prefix)
            storage_start = storage_cursor
            storage_chunks.append(replacement_text)
            storage_cursor += len(replacement_text)
            replacements.append(
                TextPositionReplacement(
                    display_start=display_range.start,
                    display_stop=display_range.stop,
                    storage_start=storage_start,
                    storage_stop=storage_cursor,
                )
            )
            display_cursor = display_range.stop
        suffix = display_text[display_cursor:]
        storage_chunks.append(suffix)
        storage_cursor += len(suffix)
        return "".join(storage_chunks), cls(
            display_length=len(display_text),
            storage_length=storage_cursor,
            replacements=tuple(replacements),
        )

    @classmethod
    def from_texts(cls, display_text, storage_text):
        """Map texts that differ only in whitespace and storage image markers."""
        if display_text == storage_text:
            return cls.identity(len(display_text))
        if TEXT_OBJECT_REPLACEMENT_CHAR in display_text:
            raise TextPositionMappingError
        display_length = len(display_text)
        storage_length = len(storage_text)
        replacements = []
        display_cursor = 0
        storage_cursor = 0
        while display_cursor < display_length or storage_cursor < storage_length:
            if (
                display_cursor < display_length
                and storage_cursor < storage_length
                and display_text[display_cursor] == storage_text[storage_cursor]
            ):
                display_cursor += 1
                storage_cursor += 1
                continue

            display_start = display_cursor
            storage_start = storage_cursor
            while display_cursor < display_length and display_text[display_cursor].isspace():
                display_cursor += 1
            while storage_cursor < storage_length and (
                storage_text[storage_cursor].isspace()
                or storage_text[storage_cursor] == TEXT_OBJECT_REPLACEMENT_CHAR
            ):
                storage_cursor += 1

            if display_cursor < display_length and storage_cursor < storage_length:
                if display_text[display_cursor] != storage_text[storage_cursor]:
                    raise TextPositionMappingError
            elif display_cursor != display_length or storage_cursor != storage_length:
                raise TextPositionMappingError

            while (
                display_cursor > display_start
                and storage_cursor > storage_start
                and display_text[display_cursor - 1] == storage_text[storage_cursor - 1]
            ):
                display_cursor -= 1
                storage_cursor -= 1

            replacements.append(
                TextPositionReplacement(
                    display_start=display_start,
                    display_stop=display_cursor,
                    storage_start=storage_start,
                    storage_stop=storage_cursor,
                )
            )
        return cls(
            display_length=display_length,
            storage_length=storage_length,
            replacements=tuple(replacements),
        )

    @staticmethod
    def _clamp(pos):
        return max(pos, 0)

    def display_to_storage_position(self, pos, affinity="before"):
        pos = self._clamp(pos)
        delta = 0
        for replacement in self.replacements:
            if pos < replacement.display_start:
                break
            if (
                replacement.display_length == 0
                and pos == replacement.display_start
            ):
                return (
                    replacement.storage_stop if affinity == "after" else replacement.storage_start
                )
            if replacement.display_start <= pos < replacement.display_stop:
                return (
                    replacement.storage_stop if affinity == "after" else replacement.storage_start
                )
            delta += replacement.display_length - replacement.storage_length
        return self._clamp(pos - delta)

    def storage_to_display_position(self, pos, affinity="before"):
        pos = self._clamp(pos)
        delta = 0
        for replacement in self.replacements:
            if pos < replacement.storage_start:
                break
            if (
                replacement.storage_length == 0
                and pos == replacement.storage_start
            ):
                return (
                    replacement.display_stop if affinity == "after" else replacement.display_start
                )
            if replacement.storage_start <= pos < replacement.storage_stop:
                return (
                    replacement.display_stop if affinity == "after" else replacement.display_start
                )
            delta += replacement.display_length - replacement.storage_length
        return self._clamp(pos + delta)

    def _display_to_storage_range_stop(self, pos):
        pos = self._clamp(pos)
        delta = 0
        for replacement in self.replacements:
            if pos < replacement.display_start:
                break
            if pos == replacement.display_start:
                return self._clamp(pos - delta)
            if replacement.display_start < pos < replacement.display_stop:
                return replacement.storage_stop
            delta += replacement.display_length - replacement.storage_length
        return self._clamp(pos - delta)

    def _storage_to_display_range_stop(self, pos):
        pos = self._clamp(pos)
        delta = 0
        for replacement in self.replacements:
            if pos < replacement.storage_start:
                break
            if pos == replacement.storage_start:
                return self._clamp(pos + delta)
            if replacement.storage_start < pos < replacement.storage_stop:
                return replacement.display_stop
            delta += replacement.display_length - replacement.storage_length
        return self._clamp(pos + delta)

    def display_to_storage_range(self, start, stop):
        start_affinity = "before"
        if start < stop:
            for replacement in self.replacements:
                if start < replacement.display_start:
                    break
                if (
                    replacement.display_length == 0
                    and start == replacement.display_start
                ):
                    start_affinity = "after"
                    break
        storage_start = self.display_to_storage_position(start, affinity=start_affinity)
        storage_stop = self._display_to_storage_range_stop(stop)
        return TextRange(storage_start, max(storage_start, storage_stop))

    def storage_to_display_range(self, start, stop):
        display_start = self.storage_to_display_position(start, affinity="before")
        display_stop = self._storage_to_display_range_stop(stop)
        return TextRange(display_start, max(display_start, display_stop))


@attr.s(auto_attribs=True)
class TextInfo:
    """Provides basic structural information  about a blob of text
    Most of the properties have their values cached.
    """

    text: str
    """The text blob to process."""

    start_pos: int = 0
    """Starting position of the text, i.e. in a text control or a stream."""

    lang: str = "en"
    """The natural language of the text. Used in splitting the text into sentences."""

    eol: str = "\n"
    """The recognizable end-of-line sequence. Used to split the text into paragraphs."""

    sent_tokenizer: t.Any = None

    def __attrs_post_init__(self):
        if not self.text.endswith("\n"):
            self.text += "\n"
        self.sent_tokenizer = partial(segment_sentences, self.lang)

    @cached_property
    def sentence_markers(self):
        return self._record_markers(self.sentences)

    @cached_property
    def paragraph_markers(self):
        return self._record_markers(self.paragraphs)

    def split_sentences(self, paragraph):
        return self.sent_tokenizer(paragraph)

    @cached_property
    def sentences(self):
        rv = []
        all_sents = set()
        for sent in self.split_sentences(self.text):
            all_sents.add(len(sent))
            if sent.strip():
                sent_start_pos = self.start_pos + sum(all_sents) + 1
                sent_range = TextRange(sent_start_pos, sent_start_pos + len(sent))
                rv.append((sent, sent_range))
        return rv

    @cached_property
    def paragraphs(self):
        # Keep the public list-valued property for backwards compatibility.
        # Performance-sensitive callers should use iter_paragraphs() so a large
        # document is not copied into several temporary lists at once.
        return list(self.iter_paragraphs())

    def iter_paragraphs(self):
        """Yield non-empty paragraphs without materializing the whole document.

        The old implementation used splitlines(), locate(), two position lists,
        and a final paragraph list.  A multi-megabyte book could therefore use
        several times its text size and block the UI before speech even began.
        Bookworm normalizes displayed document line endings to ``\n``; scanning
        one boundary at a time also lets speech start after the first paragraph.
        """
        local_start = 0
        text_length = len(self.text)
        while local_start < text_length:
            newline_pos = self.text.find("\n", local_start)
            if newline_pos < 0:
                newline_pos = text_length
            paragraph = self.text[local_start:newline_pos]
            if paragraph.strip():
                yield (
                    paragraph,
                    TextRange(
                        start=self.start_pos + local_start,
                        stop=self.start_pos + newline_pos,
                    ),
                )
            local_start = newline_pos + 1

    def _record_markers(self, segments):
        rv = []
        for _nope, pos in segments:
            rv.append(pos)
        return rv

    @cached_property
    def configured_markers(self):
        return self.paragraph_markers

    def get_paragraph_to_the_right_of(self, pos):
        # Paragraph seeking is an interactive operation.  Find only the nearby
        # boundary instead of building and sorting markers for the entire book.
        local_pos = pos - self.start_pos
        if local_pos < 0:
            candidate_start = 0
        else:
            newline_pos = self.text.find("\n", min(local_pos, len(self.text)))
            candidate_start = newline_pos + 1 if newline_pos >= 0 else len(self.text)
        text_length = len(self.text)
        while candidate_start < text_length:
            stop = self.text.find("\n", candidate_start)
            if stop < 0:
                stop = text_length
            if self.text[candidate_start:stop].strip():
                return TextRange(
                    self.start_pos + candidate_start,
                    self.start_pos + stop,
                )
            candidate_start = stop + 1
        raise LookupError(f"Could not find a paragraph located at the right of position {pos}")

    def get_paragraph_to_the_left_of(self, pos):
        local_pos = min(max(pos - self.start_pos, 0), len(self.text))
        if local_pos <= 0:
            raise LookupError(f"Could not find a paragraph located at the left of position {pos}")

        # At a paragraph start, "left" means the preceding paragraph.  When
        # inside a paragraph, it means the paragraph containing the position.
        candidate_start = self.text.rfind("\n", 0, local_pos) + 1
        if candidate_start == local_pos:
            previous_newline = self.text.rfind("\n", 0, max(0, candidate_start - 1))
            candidate_start = previous_newline + 1

        while candidate_start >= 0:
            stop = self.text.find("\n", candidate_start)
            if stop < 0:
                stop = len(self.text)
            if candidate_start < local_pos and self.text[candidate_start:stop].strip():
                return TextRange(
                    self.start_pos + candidate_start,
                    self.start_pos + stop,
                )
            if candidate_start == 0:
                break
            previous_newline = self.text.rfind("\n", 0, max(0, candidate_start - 1))
            candidate_start = previous_newline + 1
        raise LookupError(f"Could not find a paragraph located at the left of position {pos}")

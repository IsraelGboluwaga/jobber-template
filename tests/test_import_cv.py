"""Unit tests for the Notion block-flattening walk in scripts/import_cv.py.

No real Notion API calls: a FakeClient stands in for notion_client.Client,
shaped exactly like the real client's `blocks.children.list(block_id=...)`
response so the pure flattening logic can be exercised without network access.
"""
from __future__ import annotations

import pytest

from scripts import import_cv as ic


def _rt(text: str) -> list[dict]:
    return [{"plain_text": text}]


class FakeClient:
    """Minimal stand-in for notion_client.Client: pages keyed by block id."""

    def __init__(self, pages: dict[str, list[dict]]):
        self._pages = pages
        self.blocks = self

    @property
    def children(self):
        return self

    def list(self, block_id, start_cursor=None, page_size=100):
        return {"results": self._pages.get(block_id, []), "has_more": False, "next_cursor": None}


# --- _rich_text_to_plain -------------------------------------------------------

def test_rich_text_to_plain_joins_fragments():
    rich = [{"plain_text": "Hello, "}, {"plain_text": "world."}]
    assert ic._rich_text_to_plain(rich) == "Hello, world."


def test_rich_text_to_plain_handles_none():
    assert ic._rich_text_to_plain(None) == ""


# --- _block_to_lines / _fetch_block_lines --------------------------------------

def test_flattens_headings_paragraphs_and_bullets():
    top = [
        {"type": "heading_1", "heading_1": {"rich_text": _rt("Israel Example")},
         "has_children": False, "id": "h1"},
        {"type": "paragraph", "paragraph": {"rich_text": _rt("Senior backend engineer.")},
         "has_children": False, "id": "p1"},
        {"type": "heading_2", "heading_2": {"rich_text": _rt("Experience")},
         "has_children": False, "id": "h2"},
        {"type": "bulleted_list_item",
         "bulleted_list_item": {"rich_text": _rt("Acme Corp — Senior Backend Engineer")},
         "has_children": False, "id": "b1"},
    ]
    client = FakeClient({"page-root": top})

    lines = ic._fetch_block_lines(client, "page-root")

    assert lines == [
        "# Israel Example",
        "Senior backend engineer.",
        "## Experience",
        "- Acme Corp — Senior Backend Engineer",
    ]


def test_recurses_into_nested_children_with_indent():
    top = [
        {"type": "bulleted_list_item", "bulleted_list_item": {"rich_text": _rt("Acme Corp")},
         "has_children": True, "id": "b1"},
    ]
    nested = [
        {"type": "bulleted_list_item",
         "bulleted_list_item": {"rich_text": _rt("Cut latency 40%")},
         "has_children": False, "id": "b1-1"},
    ]
    client = FakeClient({"page-root": top, "b1": nested})

    lines = ic._fetch_block_lines(client, "page-root")

    assert lines == ["- Acme Corp", "  - Cut latency 40%"]


def test_table_row_joins_cells_with_pipe():
    top = [{"type": "table_row", "table_row": {"cells": [_rt("Python"), _rt("5 years")]},
            "has_children": False, "id": "r1"}]
    client = FakeClient({"page-root": top})

    lines = ic._fetch_block_lines(client, "page-root")

    assert lines == ["Python | 5 years"]


def test_empty_paragraph_produces_no_line():
    top = [{"type": "paragraph", "paragraph": {"rich_text": []}, "has_children": False, "id": "p1"}]
    client = FakeClient({"page-root": top})

    assert ic._fetch_block_lines(client, "page-root") == []


def test_paginates_across_multiple_pages():
    class PaginatingClient:
        def __init__(self):
            self.blocks = self
            self._calls = 0

        @property
        def children(self):
            return self

        def list(self, block_id, start_cursor=None, page_size=100):
            self._calls += 1
            if start_cursor is None:
                return {
                    "results": [{"type": "paragraph", "paragraph": {"rich_text": _rt("first")},
                                 "has_children": False, "id": "p1"}],
                    "has_more": True,
                    "next_cursor": "cursor-2",
                }
            return {
                "results": [{"type": "paragraph", "paragraph": {"rich_text": _rt("second")},
                             "has_children": False, "id": "p2"}],
                "has_more": False,
                "next_cursor": None,
            }

    client = PaginatingClient()
    lines = ic._fetch_block_lines(client, "page-root")

    assert lines == ["first", "second"]
    assert client._calls == 2


# --- fetch_notion_page_text -----------------------------------------------------

def test_fetch_notion_page_text_raises_when_page_empty(monkeypatch):
    class EmptyClient(FakeClient):
        def __init__(self, auth):
            super().__init__({})

    monkeypatch.setattr("notion_client.Client", EmptyClient)

    with pytest.raises(SystemExit):
        ic.fetch_notion_page_text("page-root", "fake-token")


def test_fetch_notion_page_text_returns_flattened_text(monkeypatch):
    top = [{"type": "paragraph", "paragraph": {"rich_text": _rt("Hello resume")},
            "has_children": False, "id": "p1"}]

    class OneParagraphClient(FakeClient):
        def __init__(self, auth):
            super().__init__({"page-root": top})

    monkeypatch.setattr("notion_client.Client", OneParagraphClient)

    text = ic.fetch_notion_page_text("page-root", "fake-token")

    assert text == "Hello resume"

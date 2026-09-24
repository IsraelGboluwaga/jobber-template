"""ONE-TIME / manual helper: build data/master_cv.json from a Notion page.

NOT called by the daily run. Run it yourself whenever you update your resume,
review the printed JSON, and commit data/master_cv.json by hand.

It walks the Notion page's blocks (headings, paragraphs, bullets, tables) via
the same NOTION_TOKEN/notion-client already used for the jobs database — the
page just needs to be shared with that integration too (••• -> Connections).
Flattens them to text, structures the text into the schema with a single LLM
pass (fine here — one-time, off the hot path), writes the file, and prints it
for review.

Usage:
    export CV_NOTION_PAGE_ID=<notion-page-id>   # or pass --page-id
    export NOTION_TOKEN=...
    export DEEPSEEK_API_KEY=...
    python scripts/import_cv.py
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import MASTER_CV_PATH, load_config
from src.llm import complete, make_client

SCHEMA_HINT = {
    "contact": {"name": "", "email": "", "phone": "", "location": "",
                "links": {"github": "", "linkedin": "", "website": ""}},
    "summary": "",
    "experience": [{"company": "", "title": "", "location": "", "start": "",
                    "end": "", "highlights": [""], "stack": [""]}],
    "skills": [""],
    "education": [{"institution": "", "degree": "", "start": "", "end": ""}],
}

_HEADING_PREFIX = {"heading_1": "# ", "heading_2": "## ", "heading_3": "### "}
_BULLET_PREFIX = {"bulleted_list_item": "- ", "numbered_list_item": "- ", "to_do": "- "}


def _rich_text_to_plain(rich_text: list[dict] | None) -> str:
    return "".join(rt.get("plain_text", "") for rt in (rich_text or []))


def _fetch_block_lines(client: Any, block_id: str, depth: int = 0) -> list[str]:
    lines: list[str] = []
    cursor: str | None = None
    while True:
        resp = client.blocks.children.list(block_id=block_id, start_cursor=cursor, page_size=100)
        for block in resp.get("results", []):
            lines.extend(_block_to_lines(client, block, depth))
        if not resp.get("has_more"):
            break
        cursor = resp.get("next_cursor")
    return lines


def _block_to_lines(client: Any, block: dict, depth: int) -> list[str]:
    btype = block.get("type", "")
    data = block.get(btype, {}) or {}
    indent = "  " * depth
    lines: list[str] = []

    if btype in _HEADING_PREFIX:
        lines.append(f"{indent}{_HEADING_PREFIX[btype]}{_rich_text_to_plain(data.get('rich_text'))}")
    elif btype in _BULLET_PREFIX:
        lines.append(f"{indent}{_BULLET_PREFIX[btype]}{_rich_text_to_plain(data.get('rich_text'))}")
    elif btype == "quote":
        lines.append(f"{indent}> {_rich_text_to_plain(data.get('rich_text'))}")
    elif btype == "table_row":
        cells = data.get("cells", [])
        lines.append(indent + " | ".join(_rich_text_to_plain(c) for c in cells))
    elif btype == "paragraph":
        text = _rich_text_to_plain(data.get("rich_text"))
        if text:
            lines.append(f"{indent}{text}")
    # else (divider, image, child_page, ...): no text of its own; still recurse below.

    if block.get("has_children"):
        lines.extend(_fetch_block_lines(client, block["id"], depth + 1))

    return lines


def fetch_notion_page_text(page_id: str, token: str) -> str:
    from notion_client import Client

    client = Client(auth=token)
    try:
        lines = _fetch_block_lines(client, page_id)
    except Exception as exc:
        raise SystemExit(
            f"Notion API error fetching page {page_id}: {exc}\n"
            "Check the page id and that the page is shared with your integration "
            "(page -> ••• -> Connections -> add your integration)."
        ) from exc
    text = "\n".join(line for line in lines if line.strip())
    if not text:
        raise SystemExit(
            "Notion page returned no readable text. Check the page id and that "
            "it's shared with your integration (••• -> Connections -> add integration)."
        )
    return text


def structure_cv(text: str, cfg) -> dict:
    client = make_client(cfg)
    system = (
        "You convert a resume's plain text into strict JSON. Use ONLY facts present "
        "in the text — never invent. Output JSON only, matching this schema exactly:\n"
        + json.dumps(SCHEMA_HINT)
    )
    raw = complete(system, text[:12000], max_tokens=2000, client=client, cfg=cfg)
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        raw = raw[raw.find("\n") + 1:] if "\n" in raw else raw
    return json.loads(raw)


def main() -> int:
    parser = argparse.ArgumentParser(description="One-time: Notion page -> master_cv.json")
    parser.add_argument("--page-id", default=os.environ.get("CV_NOTION_PAGE_ID"),
                        help="Notion page id (or set CV_NOTION_PAGE_ID).")
    parser.add_argument("--out", default=str(MASTER_CV_PATH))
    args = parser.parse_args()

    if not args.page_id:
        raise SystemExit("Provide --page-id or set CV_NOTION_PAGE_ID.")

    cfg = load_config()
    if not cfg.secrets.notion_token:
        raise SystemExit("NOTION_TOKEN must be set (the same integration used for the jobs database).")

    print(f"Fetching Notion page {args.page_id}...", file=sys.stderr)
    text = fetch_notion_page_text(args.page_id, cfg.secrets.notion_token)
    print(f"Structuring {len(text)} chars into JSON via the LLM...", file=sys.stderr)
    cv = structure_cv(text, cfg)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(cv, fh, indent=2, ensure_ascii=False)

    print(f"\nWrote {args.out}. Review it below, then commit by hand:\n", file=sys.stderr)
    print(json.dumps(cv, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

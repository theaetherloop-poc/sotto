"""Build the shared Moss ``aether_kb`` index from ``sotto-agent/sotto_phase3_kb.jsonl``.

The Aether Loop question library (KB_CANDIDATES) — a global, per-line JSONL of curated Phase 3
questions. Each line needs ``id`` and ``text``; ``phase3_section`` / ``conditional_on`` /
``trigger_topics`` / ``cfa`` / ``type`` are carried as metadata (stringified, since Moss metadata
values must be strings). The doc ``id`` is the question id, so a retrieved candidate maps directly
to a ``kb_id`` on the card.

Run from sotto-agent/ via:

    uv run src/sotto/scripts/build_aether_kb.py

Requires MOSS_PROJECT_ID / MOSS_PROJECT_KEY in .env.local; without them it exits with a clear
message instead of contacting Moss.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from moss import DocumentInfo, MossClient

# src/sotto/scripts/build_aether_kb.py -> parents[3] == sotto-agent/
AGENT_DIR = Path(__file__).resolve().parents[3]
KB_PATH = AGENT_DIR / "sotto_phase3_kb.jsonl"
ENV_PATH = AGENT_DIR / ".env.local"

DEFAULT_MODEL_ID = "moss-minilm"
DEFAULT_AETHER_INDEX = "aether_kb"

load_dotenv(ENV_PATH)


def _stringify(value) -> str:
    """Moss metadata values must be strings; flatten lists to comma-joined text."""
    if isinstance(value, (list, tuple)):
        return ",".join(str(v) for v in value)
    return str(value)


def _load_kb_documents() -> list[DocumentInfo]:
    if not KB_PATH.exists():
        raise FileNotFoundError(f"Aether KB data file not found at {KB_PATH}.")

    documents: list[DocumentInfo] = []
    with KB_PATH.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on line {line_no} of {KB_PATH}: {exc}") from exc
            doc_id = entry.get("id")
            text = entry.get("text")
            if not doc_id or not text:
                continue
            metadata = {
                k: _stringify(v)
                for k, v in entry.items()
                if k not in ("id", "text") and v not in (None, "", [])
            }
            documents.append(DocumentInfo(id=str(doc_id), text=str(text), metadata=metadata))

    if not documents:
        raise ValueError("No valid documents were loaded from sotto_phase3_kb.jsonl.")

    return documents


async def build_index() -> None:
    project_id = os.getenv("MOSS_PROJECT_ID")
    project_key = os.getenv("MOSS_PROJECT_KEY")
    aether_index = os.getenv("MOSS_AETHER_INDEX_NAME", DEFAULT_AETHER_INDEX)
    model_id = os.getenv("MOSS_MODEL_ID", DEFAULT_MODEL_ID)

    missing = [
        name
        for name, value in {
            "MOSS_PROJECT_ID": project_id,
            "MOSS_PROJECT_KEY": project_key,
        }.items()
        if not value
    ]
    if missing:
        raise OSError(
            "Missing required Moss environment variables: "
            + ", ".join(missing)
            + f". Set them in {ENV_PATH} before running this script."
        )

    assert project_id is not None
    assert project_key is not None

    docs = _load_kb_documents()
    client = MossClient(project_id, project_key)

    # Idempotent rebuild: drop any existing index so re-seeding fully replaces its docs.
    try:
        await client.delete_index(aether_index)
        print(f"Deleted existing index '{aether_index}' before rebuild.")
    except Exception:
        pass

    print(
        f"Creating Moss Aether KB index '{aether_index}' with {len(docs)} questions "
        f"using model '{model_id}'..."
    )
    result = await client.create_index(aether_index, docs, model_id)
    print(f"  done (job: {result.job_id}, index: {result.index_name}, docs: {result.doc_count})")
    print("Aether KB ready. Sotto will retrieve KB_CANDIDATES from it at runtime.")


if __name__ == "__main__":
    asyncio.run(build_index())

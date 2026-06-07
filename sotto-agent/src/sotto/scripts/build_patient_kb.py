"""Build the Moss patient-context index from ``sotto-agent/patient_kb.json``.

Mirrors agent-py's ``create_index.py``: reads a JSON list of patient history documents and
(re)creates the ``patient_context`` index that Sotto queries at runtime for PATIENT_CONTEXT.

Each entry needs ``id``, ``text``, and a ``metadata`` object that includes ``patient_id`` (used by
the per-patient query filter). Run from sotto-agent/ via:

    uv run src/sotto/scripts/build_patient_kb.py

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

# src/sotto/scripts/build_patient_kb.py -> parents[3] == sotto-agent/
AGENT_DIR = Path(__file__).resolve().parents[3]
KB_PATH = AGENT_DIR / "patient_kb.json"
ENV_PATH = AGENT_DIR / ".env.local"

DEFAULT_MODEL_ID = "moss-minilm"
DEFAULT_PATIENT_INDEX = "patient_context"

load_dotenv(ENV_PATH)


def _load_patient_documents() -> list[DocumentInfo]:
    if not KB_PATH.exists():
        raise FileNotFoundError(f"Patient KB data file not found at {KB_PATH}.")

    with KB_PATH.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    if not isinstance(data, list):
        raise ValueError("patient_kb.json must be a list of document entries.")

    documents: list[DocumentInfo] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        doc_id = entry.get("id")
        text = entry.get("text")
        if not doc_id or not text:
            continue
        metadata = entry.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        # Moss metadata values must be strings.
        metadata = {str(k): str(v) for k, v in metadata.items()}
        if "patient_id" not in metadata:
            raise ValueError(f"Document {doc_id!r} is missing required metadata key 'patient_id'.")
        documents.append(DocumentInfo(id=str(doc_id), text=str(text), metadata=metadata))

    if not documents:
        raise ValueError("No valid documents were loaded from patient_kb.json.")

    return documents


async def build_index() -> None:
    project_id = os.getenv("MOSS_PROJECT_ID")
    project_key = os.getenv("MOSS_PROJECT_KEY")
    patient_index = os.getenv("MOSS_PATIENT_INDEX_NAME", DEFAULT_PATIENT_INDEX)
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

    docs = _load_patient_documents()
    client = MossClient(project_id, project_key)

    # Idempotent rebuild: drop any existing index so re-seeding fully replaces its docs.
    try:
        await client.delete_index(patient_index)
        print(f"Deleted existing index '{patient_index}' before rebuild.")
    except Exception:
        pass

    print(
        f"Creating Moss patient index '{patient_index}' with {len(docs)} docs "
        f"using model '{model_id}'..."
    )
    result = await client.create_index(patient_index, docs, model_id)
    print(f"  done (job: {result.job_id}, index: {result.index_name}, docs: {result.doc_count})")
    print("Patient context index ready. Sotto will retrieve from it at runtime.")


if __name__ == "__main__":
    asyncio.run(build_index())

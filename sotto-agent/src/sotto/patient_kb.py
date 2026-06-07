"""Patient knowledge base — Moss-backed retrieval of a patient's past clinical context.

Sotto queries this on each cue evaluation with the recent transcript window and injects the
retrieved snippets into the cue-engine prompt under a PATIENT_CONTEXT block. The cue prompt is
already written to treat PATIENT_CONTEXT as the only required per-patient input and to cite the
source, so this module is what actually supplies that data (Phase 1 invented it).

Scoped to a single patient via a ``patient_id`` metadata filter so one consult never retrieves
another patient's records — the same isolation pattern agent-py uses for per-user memory.
"""

from __future__ import annotations

import logging
import os

from moss import MossClient, QueryOptions

logger = logging.getLogger(__name__)

# Index holding patient history docs; built by scripts/build_patient_kb.py. Overridable so the
# seeder and the agent stay in sync.
PATIENT_INDEX = os.getenv("MOSS_PATIENT_INDEX_NAME", "patient_context")
# Fixed demo patient for now. A real deployment would resolve this per consult.
DEFAULT_PATIENT_ID = os.getenv("SOTTO_PATIENT_ID", "patient_demo")


class PatientKB:
    """Patient-scoped semantic search over the Moss ``patient_context`` index."""

    def __init__(
        self,
        patient_id: str = DEFAULT_PATIENT_ID,
        *,
        index_name: str = PATIENT_INDEX,
        client: MossClient | None = None,
    ) -> None:
        self._patient_id = patient_id
        self._index = index_name
        self._moss = client or MossClient(
            os.getenv("MOSS_PROJECT_ID"), os.getenv("MOSS_PROJECT_KEY")
        )
        self._loaded = False
        self._summary: str | None = None

    async def load(self) -> None:
        """Preload the index so the first query is fast. Guarded: logs and continues on failure."""
        if self._loaded:
            return
        try:
            await self._moss.load_index(self._index)
            self._loaded = True
            logger.info("Loaded patient KB index '%s'", self._index)
        except Exception:
            logger.exception("Failed to load patient KB index '%s'; will retry on use", self._index)

    async def load_summary(self) -> str:
        """Fetch this patient's full Phase 1+2 intake as a single PATIENT_CONTEXT block.

        The spec injects the whole intake summary on every cue evaluation (it's compact), so we
        fetch all of the patient's docs once and cache the formatted block. Implemented as a broad,
        high-``top_k`` query filtered to the patient — Moss has no list-by-filter, and for a small
        per-patient intake this returns every doc. Returns "" (cached) on error so the agent runs
        without inventing patient data.
        """
        if self._summary is not None:
            return self._summary
        if not self._loaded:
            await self.load()
        try:
            result = await self._moss.query(
                self._index,
                "patient intake history summary",
                QueryOptions(
                    top_k=100,
                    filter={
                        "field": "patient_id",
                        "condition": {"$eq": self._patient_id},
                    },
                ),
            )
        except Exception:
            logger.exception("patient KB summary load failed; proceeding without patient context")
            self._summary = ""
            return self._summary

        docs = list(getattr(result, "docs", None) or [])
        # Stable order (by doc id) so the injected summary is deterministic across sessions.
        docs.sort(key=lambda d: getattr(d, "id", "") or "")
        snippets: list[dict] = []
        for doc in docs:
            text = (getattr(doc, "text", "") or "").strip()
            if not text:
                continue
            metadata = getattr(doc, "metadata", None) or {}
            snippets.append({"text": text, "source": metadata.get("source")})
        self._summary = format_patient_context(snippets)
        return self._summary

    async def retrieve(self, query: str, *, top_k: int = 3) -> list[dict]:
        """Return up to ``top_k`` patient-context snippets matching ``query``, scoped to this patient.

        Each snippet is ``{"text": str, "source": str | None}``. Returns an empty list on no match
        or any error, so the cue engine degrades gracefully — the prompt treats absent
        PATIENT_CONTEXT as "not available" rather than inventing data.
        """
        if not query.strip():
            return []
        if not self._loaded:
            await self.load()
        try:
            result = await self._moss.query(
                self._index,
                query,
                QueryOptions(
                    top_k=top_k,
                    filter={
                        "field": "patient_id",
                        "condition": {"$eq": self._patient_id},
                    },
                ),
            )
        except Exception:
            logger.exception("patient KB query failed; proceeding without patient context")
            return []

        snippets: list[dict] = []
        for doc in getattr(result, "docs", None) or []:
            text = (getattr(doc, "text", "") or "").strip()
            if not text:
                continue
            metadata = getattr(doc, "metadata", None) or {}
            snippets.append({"text": text, "source": metadata.get("source")})
        return snippets


def format_patient_context(snippets: list[dict]) -> str:
    """Render retrieved snippets into the PATIENT_CONTEXT block the cue-engine prompt expects.

    Returns an empty string when there are no snippets, which the caller uses to omit the block
    entirely (so the LLM sees nothing rather than an empty heading).
    """
    if not snippets:
        return ""
    lines = []
    for snippet in snippets:
        source = snippet.get("source")
        prefix = f"[{source}] " if source else ""
        lines.append(f"- {prefix}{snippet['text']}")
    return (
        "PATIENT_CONTEXT (completed Phase 1 + Phase 2 intake — cite the source when surfacing "
        "a card):\n" + "\n".join(lines)
    )

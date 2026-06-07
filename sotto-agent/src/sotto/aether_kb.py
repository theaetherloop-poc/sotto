"""Aether Loop question library — the shared KB_CANDIDATES grounding source.

A curated superset of the questions functional-medicine practitioners ask, organized by Phase 3
section. Unlike the per-patient ``patient_context`` index, this one is GLOBAL: every consult
queries the same library. Sotto retrieves the candidates most relevant to the recent transcript
and injects them as KB_CANDIDATES; the cue prompt prefers them and surfaces a ``source="kb"`` card
with ``kb_id`` set to the candidate's id.

Built offline from ``sotto-agent/sotto_phase3_kb.jsonl`` by scripts/build_aether_kb.py.
"""

from __future__ import annotations

import logging
import os

from moss import MossClient, QueryOptions

logger = logging.getLogger(__name__)

# Shared question-library index. Overridable so the seeder and the agent stay in sync.
AETHER_INDEX = os.getenv("MOSS_AETHER_INDEX_NAME", "aether_kb")


class KbLibrary:
    """Semantic search over the shared Aether Loop question library (KB_CANDIDATES)."""

    def __init__(self, *, index_name: str = AETHER_INDEX, client: MossClient | None = None) -> None:
        self._index = index_name
        self._moss = client or MossClient(
            os.getenv("MOSS_PROJECT_ID"), os.getenv("MOSS_PROJECT_KEY")
        )
        self._loaded = False

    async def load(self) -> None:
        """Preload the index so the first query is fast. Guarded: logs and continues on failure."""
        if self._loaded:
            return
        try:
            await self._moss.load_index(self._index)
            self._loaded = True
            logger.info("Loaded Aether KB index '%s'", self._index)
        except Exception:
            logger.exception("Failed to load Aether KB index '%s'; will retry on use", self._index)

    async def retrieve(self, query: str, *, top_k: int = 5) -> list[dict]:
        """Return up to ``top_k`` library questions most relevant to ``query``.

        Each candidate is ``{"id", "text", "phase3_section", "conditional_on", "trigger_topics"}``.
        Returns an empty list on no match or any error so the cue engine degrades gracefully
        (it can still emit ``source="adaptive"`` cards with no library to ground on).
        """
        if not query.strip():
            return []
        if not self._loaded:
            await self.load()
        try:
            result = await self._moss.query(self._index, query, QueryOptions(top_k=top_k))
        except Exception:
            logger.exception("Aether KB query failed; proceeding without KB candidates")
            return []

        candidates: list[dict] = []
        for doc in getattr(result, "docs", None) or []:
            text = (getattr(doc, "text", "") or "").strip()
            if not text:
                continue
            metadata = getattr(doc, "metadata", None) or {}
            candidates.append(
                {
                    "id": getattr(doc, "id", None) or metadata.get("kb_id"),
                    "text": text,
                    "phase3_section": metadata.get("phase3_section"),
                    "conditional_on": metadata.get("conditional_on"),
                    "trigger_topics": metadata.get("trigger_topics"),
                }
            )
        return candidates


def format_kb_candidates(candidates: list[dict]) -> str:
    """Render KB candidates into the KB_CANDIDATES block the cue-engine prompt expects.

    Includes id / section / trigger metadata so the model can prefer a candidate whose trigger
    fits this patient — but NOT the ``cfa`` focus areas, which belong to the recommendation engine
    and must never reach the live card. Returns "" when there are no candidates.
    """
    if not candidates:
        return ""
    lines = []
    for cand in candidates:
        meta_bits = [f"id={cand.get('id')}"]
        if cand.get("phase3_section"):
            meta_bits.append(f"section={cand['phase3_section']}")
        if cand.get("conditional_on"):
            meta_bits.append(f"when={cand['conditional_on']}")
        if cand.get("trigger_topics"):
            meta_bits.append(f"topics={cand['trigger_topics']}")
        lines.append(f"- [{' | '.join(meta_bits)}] {cand['text']}")
    return (
        'KB_CANDIDATES (Aether Loop library — prefer these; if you surface one, set source="kb" '
        "and kb_id to its id):\n" + "\n".join(lines)
    )

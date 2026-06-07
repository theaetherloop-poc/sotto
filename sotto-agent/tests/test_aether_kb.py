"""Unit tests for KbLibrary: KB_CANDIDATES retrieval shape, kb_id mapping, block formatting.

Stubs MossClient so these run with no Moss credentials and no network.
"""

from __future__ import annotations

from sotto.aether_kb import KbLibrary, format_kb_candidates


class _FakeDoc:
    def __init__(self, doc_id, text, metadata=None, score=1.0) -> None:
        self.id = doc_id
        self.text = text
        self.metadata = metadata
        self.score = score


class _FakeResult:
    def __init__(self, docs) -> None:
        self.docs = docs


class _FakeMossClient:
    def __init__(self, *args, **kwargs) -> None:
        self.load_index_calls: list[str] = []
        self.query_calls: list[tuple] = []
        self.query_result = _FakeResult([])
        self.raise_on_query = False

    async def load_index(self, name, *args, **kwargs):
        self.load_index_calls.append(name)

    async def query(self, index, query, options=None):
        self.query_calls.append((index, query, options))
        if self.raise_on_query:
            raise RuntimeError("moss unavailable")
        return self.query_result


def _lib(client) -> KbLibrary:
    return KbLibrary(index_name="aether_kb", client=client)


async def test_retrieve_returns_candidate_shape_with_id() -> None:
    client = _FakeMossClient()
    client.query_result = _FakeResult(
        [
            _FakeDoc(
                "goals_last_well",
                "When did you last feel really well, in body and mind?",
                {
                    "phase3_section": "Goals & Narrative",
                    "conditional_on": "always",
                    "trigger_topics": "timeline",
                    "cfa": "",
                },
                score=0.97,
            )
        ]
    )
    lib = _lib(client)

    candidates = await lib.retrieve("patient says they haven't felt right in months")

    # Library is global — queried with no per-patient filter.
    assert client.load_index_calls == ["aether_kb"]
    index, query, options = client.query_calls[0]
    assert index == "aether_kb"
    assert getattr(options, "filter", None) is None

    assert candidates == [
        {
            "id": "goals_last_well",
            "text": "When did you last feel really well, in body and mind?",
            "score": 0.97,
            "phase3_section": "Goals & Narrative",
            "conditional_on": "always",
            "trigger_topics": "timeline",
        }
    ]


async def test_retrieve_drops_below_threshold_candidate() -> None:
    client = _FakeMossClient()
    client.query_result = _FakeResult(
        [
            _FakeDoc(
                "off_topic",
                "Some loosely related chit-chat question.",
                {"phase3_section": "Goals & Narrative"},
                score=0.90,
            )
        ]
    )
    lib = _lib(client)

    # 0.90 is below the default 0.93 gate → nothing injected.
    assert await lib.retrieve("unrelated small talk") == []


async def test_retrieve_empty_query_skips_moss() -> None:
    client = _FakeMossClient()
    lib = _lib(client)
    assert await lib.retrieve("  ") == []
    assert client.query_calls == []


async def test_retrieve_returns_empty_on_error() -> None:
    client = _FakeMossClient()
    client.raise_on_query = True
    lib = _lib(client)
    assert await lib.retrieve("anything") == []


def test_format_kb_candidates_empty_is_blank() -> None:
    assert format_kb_candidates([]) == ""


def test_format_kb_candidates_carries_id_and_section_not_cfa() -> None:
    block = format_kb_candidates(
        [
            {
                "id": "goals_last_well",
                "text": "When did you last feel really well?",
                "phase3_section": "Goals & Narrative",
                "conditional_on": "always",
                "trigger_topics": "timeline",
            }
        ]
    )
    assert block.startswith("KB_CANDIDATES")
    # id is present so the model can map a kb card to its kb_id.
    assert "id=goals_last_well" in block
    assert "section=Goals & Narrative" in block
    assert "When did you last feel really well?" in block
    # cfa focus areas belong to the recommendation engine — never injected.
    assert "cfa" not in block

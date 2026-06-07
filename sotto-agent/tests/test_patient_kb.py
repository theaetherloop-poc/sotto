"""Unit tests for PatientKB: per-patient query filtering, snippet shaping, graceful failure.

Stubs MossClient so these run with no Moss credentials and no network — the live, credentialed
behavior is validated against the real index separately.
"""

from __future__ import annotations

from sotto.patient_kb import PatientKB, format_patient_context

PATIENT_ID = "patient_demo"


class _FakeDoc:
    def __init__(self, text, metadata=None) -> None:
        self.text = text
        self.metadata = metadata


class _FakeResult:
    def __init__(self, docs) -> None:
        self.docs = docs


class _FakeMossClient:
    """Records calls instead of contacting Moss."""

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


def _kb(client) -> PatientKB:
    return PatientKB(PATIENT_ID, index_name="patient_context", client=client)


async def test_retrieve_filters_by_patient_id() -> None:
    client = _FakeMossClient()
    client.query_result = _FakeResult(
        [
            _FakeDoc("TSH high-normal, TPO mildly elevated.", {"source": "lab report"}),
            _FakeDoc("Persistent fatigue for 8 months.", {"source": "intake form"}),
        ]
    )
    kb = _kb(client)

    snippets = await kb.retrieve("patient feels tired and foggy")

    # Loaded then queried the patient_context index.
    assert client.load_index_calls == ["patient_context"]
    assert len(client.query_calls) == 1
    index, query, options = client.query_calls[0]
    assert index == "patient_context"
    assert query == "patient feels tired and foggy"
    assert options.top_k == 3
    # Per-patient isolation: the filter pins patient_id to this consult.
    assert options.filter == {
        "field": "patient_id",
        "condition": {"$eq": PATIENT_ID},
    }

    assert snippets == [
        {"text": "TSH high-normal, TPO mildly elevated.", "source": "lab report"},
        {"text": "Persistent fatigue for 8 months.", "source": "intake form"},
    ]


async def test_retrieve_skips_empty_query_without_calling_moss() -> None:
    client = _FakeMossClient()
    kb = _kb(client)

    assert await kb.retrieve("   ") == []
    assert client.query_calls == []


async def test_retrieve_returns_empty_on_moss_error() -> None:
    client = _FakeMossClient()
    client.raise_on_query = True
    kb = _kb(client)

    # Degrades gracefully so the cue engine proceeds with no patient context.
    assert await kb.retrieve("anything") == []


async def test_retrieve_drops_blank_snippets() -> None:
    client = _FakeMossClient()
    client.query_result = _FakeResult([_FakeDoc("   ", {"source": "x"}), _FakeDoc("real")])
    kb = _kb(client)

    snippets = await kb.retrieve("q")
    assert snippets == [{"text": "real", "source": None}]


async def test_load_summary_joins_all_patient_docs_and_caches() -> None:
    client = _FakeMossClient()
    client.query_result = _FakeResult(
        [
            _FakeDoc("Thyroid panel: TSH high-normal.", {"source": "lab report"}),
            _FakeDoc("Persistent fatigue for 8 months.", {"source": "intake form"}),
        ]
    )
    kb = _kb(client)

    summary = await kb.load_summary()

    assert summary.startswith("PATIENT_CONTEXT")
    assert "TSH high-normal" in summary
    assert "Persistent fatigue" in summary
    # Full-intake fetch is patient-scoped with a high top_k.
    index, _query, options = client.query_calls[0]
    assert index == "patient_context"
    assert options.top_k == 100
    assert options.filter == {"field": "patient_id", "condition": {"$eq": PATIENT_ID}}

    # Cached: a second call does not re-query Moss.
    await kb.load_summary()
    assert len(client.query_calls) == 1


def test_format_patient_context_empty_is_blank() -> None:
    assert format_patient_context([]) == ""


def test_format_patient_context_renders_block_with_sources() -> None:
    block = format_patient_context(
        [
            {"text": "TSH 4.8, TPO elevated.", "source": "lab report"},
            {"text": "Fatigue 8 months.", "source": None},
        ]
    )
    assert block.startswith("PATIENT_CONTEXT")
    assert "- [lab report] TSH 4.8, TPO elevated." in block
    assert "- Fatigue 8 months." in block

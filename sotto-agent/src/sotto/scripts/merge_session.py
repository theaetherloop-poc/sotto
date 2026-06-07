"""Merge a Sotto session's transcript + cue logs into one timestamped, readable timeline.

Reads the two append-only logs the agent writes during a session:

* ``logs/sotto-transcript.jsonl`` — one ``{timestamp, speaker, text}`` per final utterance.
* ``logs/sotto-cues.jsonl``       — one card dict per emit (incl. ``transcript_snippet``,
  ``triggered_by_speaker``, ``triggered_at``, ``usefulness``).

and produces:

1. A Markdown timeline (cues indented under the utterance that triggered them), and
2. A trigger -> card LATENCY report: for each card, the utterance it was grounded in and the
   seconds between that utterance and the card emit. This is the "cue generation at exact time"
   view used to evaluate the orchestration.

Run AFTER a session (the agent must have finished writing the logs):

    uv run python -m sotto.scripts.merge_session
    # or with explicit paths:
    uv run python -m sotto.scripts.merge_session \
        --transcript logs/sotto-transcript.jsonl \
        --cues logs/sotto-cues.jsonl \
        --out logs/sotto-session-readable.md
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

_TYPE_EMOJI = {
    "suggested_question": "💡",
    "protocol_direction": "🩺",
    "patient_context": "📋",
}
_SPEAKER_ABBR = {"doctor": "D", "patient": "P"}

# Same grounding heuristic the cue engine uses: a snippet matches an utterance when enough of
# its words appear in that utterance (order-insensitive, punctuation-tolerant).
_MATCH_MIN_OVERLAP = 0.5


def _normalize(text: str) -> list[str]:
    return "".join(c if c.isalnum() or c.isspace() else " " for c in text.lower()).split()


def _overlap(snippet: str, text: str) -> float:
    snip = _normalize(snippet)
    if not snip:
        return 0.0
    words = set(_normalize(text))
    return sum(1 for t in snip if t in words) / len(snip)


@dataclass
class Utterance:
    ts: datetime
    speaker: str
    text: str


@dataclass
class Cue:
    ts: datetime
    card: dict
    anchor: Utterance | None = None  # best snippet match at/before ts
    latency_s: float | None = None


def _parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _load_transcript(path: Path) -> list[Utterance]:
    out: list[Utterance] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        out.append(Utterance(_parse_ts(obj["timestamp"]), obj["speaker"], obj["text"]))
    out.sort(key=lambda u: u.ts)
    return out


def _load_cues(path: Path) -> list[Cue]:
    out: list[Cue] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        out.append(Cue(_parse_ts(obj["triggered_at"]), obj))
    out.sort(key=lambda c: c.ts)
    return out


def _anchor_cues(utterances: list[Utterance], cues: list[Cue]) -> None:
    """For each cue, find the utterance its snippet was grounded in and compute latency.

    Candidate = an utterance at or before the cue's emit time. Among those, the best token
    overlap with the snippet wins (tie broken by recency). Falls back to the most recent
    utterance before the emit when no snippet overlaps (latency still meaningful)."""
    for cue in cues:
        snippet = cue.card.get("transcript_snippet", "") or ""
        best: Utterance | None = None
        best_score = 0.0
        fallback: Utterance | None = None
        for utt in utterances:
            if utt.ts > cue.ts:
                break
            fallback = utt  # most recent utterance at/before emit
            score = _overlap(snippet, utt.text)
            if score >= _MATCH_MIN_OVERLAP and score >= best_score:
                best, best_score = utt, score
        cue.anchor = best or fallback
        if cue.anchor is not None:
            cue.latency_s = (cue.ts - cue.anchor.ts).total_seconds()


def _fmt_clock(ts: datetime) -> str:
    return ts.strftime("%H:%M:%S")


def _render(utterances: list[Utterance], cues: list[Cue]) -> str:
    # Group cues by the utterance they're anchored to so we can indent them inline.
    cues_by_anchor: dict[int, list[Cue]] = {}
    orphan_cues: list[Cue] = []
    for cue in cues:
        if cue.anchor is None:
            orphan_cues.append(cue)
        else:
            cues_by_anchor.setdefault(id(cue.anchor), []).append(cue)

    lines: list[str] = [
        "# Sotto Session — Transcript & Cues",
        "",
        "**Speakers:** `D` = doctor · `P` = patient",
        "**Cue types:** 💡 Suggested Question · 🩺 Protocol Direction · 📋 Patient Context",
        "All timestamps are UTC. Each cue is indented under the utterance it was grounded in, "
        "with `Δ` = seconds from that utterance to the card appearing.",
        "",
        "---",
        "",
        "## Timeline",
        "",
    ]
    for utt in utterances:
        abbr = _SPEAKER_ABBR.get(utt.speaker, utt.speaker)
        lines.append(f"- `{_fmt_clock(utt.ts)}` **{abbr}:** {utt.text}")
        for cue in cues_by_anchor.get(id(utt), []):
            lines.append(_render_cue(cue))
    if orphan_cues:
        lines.append("")
        lines.append("### Unanchored cues (no matching utterance found)")
        for cue in orphan_cues:
            lines.append(_render_cue(cue))

    lines.extend(_render_latency_report(cues))
    return "\n".join(lines) + "\n"


def _render_cue(cue: Cue) -> str:
    card = cue.card
    emoji = _TYPE_EMOJI.get(card.get("type", ""), "•")
    src = card.get("source", "?")
    use = card.get("usefulness")
    use_str = f" · useful={use:.2f}" if isinstance(use, (int, float)) else ""
    delta = f" · Δ{cue.latency_s:.1f}s" if cue.latency_s is not None else ""
    by = card.get("triggered_by_speaker", "?")
    head = (
        f"  - {emoji} `{_fmt_clock(cue.ts)}` **Cue** "
        f"(src={src}{use_str}{delta}, trigger={by}) — *{card.get('content', '')}*"
    )
    rationale = card.get("rationale", "")
    snippet = card.get("transcript_snippet", "")
    return head + (
        f"\n    *Rationale:* {rationale}"
        f"\n    *Snippet:* “{snippet}”"
    )


def _render_latency_report(cues: list[Cue]) -> list[str]:
    lines = ["", "---", "", "## Trigger → Card latency", ""]
    if not cues:
        lines.append("_No cues emitted._")
        return lines
    lines.append("| emit (UTC) | type | src | useful | Δ trigger→card | trigger utterance |")
    lines.append("|---|---|---|---|---|---|")
    latencies: list[float] = []
    for cue in cues:
        card = cue.card
        use = card.get("usefulness")
        use_str = f"{use:.2f}" if isinstance(use, (int, float)) else "—"
        if cue.latency_s is not None:
            latencies.append(cue.latency_s)
            delta = f"{cue.latency_s:.1f}s"
        else:
            delta = "—"
        trig = cue.anchor.text if cue.anchor else "(none)"
        trig = trig.replace("|", "\\|")
        if len(trig) > 60:
            trig = trig[:57] + "…"
        lines.append(
            f"| {_fmt_clock(cue.ts)} | {card.get('type', '?')} | {card.get('source', '?')} "
            f"| {use_str} | {delta} | {trig} |"
        )
    if latencies:
        latencies.sort()
        n = len(latencies)
        p50 = latencies[n // 2]
        mx = latencies[-1]
        mean = sum(latencies) / n
        lines.extend(
            [
                "",
                f"**Cards:** {len(cues)} · **latency** mean={mean:.1f}s "
                f"median={p50:.1f}s max={mx:.1f}s",
            ]
        )
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transcript", default="logs/sotto-transcript.jsonl")
    parser.add_argument("--cues", default="logs/sotto-cues.jsonl")
    parser.add_argument("--out", default="logs/sotto-session-readable.md")
    args = parser.parse_args()

    t_path, c_path = Path(args.transcript), Path(args.cues)
    if not t_path.exists():
        print(f"Transcript log not found: {t_path}", file=sys.stderr)
        return 1
    utterances = _load_transcript(t_path)
    cues = _load_cues(c_path) if c_path.exists() else []
    _anchor_cues(utterances, cues)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(_render(utterances, cues), encoding="utf-8")
    print(
        f"Wrote {out_path} — {len(utterances)} utterances, {len(cues)} cues.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

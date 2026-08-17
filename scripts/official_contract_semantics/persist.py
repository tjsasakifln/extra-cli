"""Append-only JSONL store. Reprocessing never overwrites a previous observation."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from scripts.official_contract_semantics.models import OfficialContractObservation, observation_from_mapping
from scripts.official_contract_semantics.serialize import canonical_dumps, load_jsonl, sha256_text


def load_store(path: str | Path) -> tuple[OfficialContractObservation, ...]:
    target = Path(path)
    if not target.exists():
        return ()
    rows = load_jsonl(target)
    return tuple(observation_from_mapping(row) for row in rows)


def append_observations(
    path: str | Path,
    observations: Iterable[OfficialContractObservation],
) -> tuple[tuple[OfficialContractObservation, ...], str]:
    target = Path(path)
    existing = {item.observation_id: item for item in load_store(target)}
    for item in observations:
        if item.observation_id in existing:
            continue
        existing[item.observation_id] = item
    ordered = tuple(sorted(existing.values(), key=lambda item: item.observation_id))
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [canonical_dumps(item.as_dict()) for item in ordered]
    text = ("\n".join(lines) + "\n") if lines else ""
    target.write_text(text, encoding="utf-8")
    return ordered, sha256_text(text)

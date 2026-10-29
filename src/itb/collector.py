"""Block collection: fetch raw getBlock JSON and locate our signatures.

The raw block JSON is stored verbatim (that is the verifiable evidence);
position extraction is a pure function over that JSON so it is unit-testable
with canned payloads and re-runnable by anyone.
"""

from __future__ import annotations

import json
from pathlib import Path


def extract_positions(block: dict, signatures: set[str]) -> dict[str, int]:
    """Map each of our signatures found in the block to its 0-based index in
    the block's transaction list."""
    out: dict[str, int] = {}
    for idx, tx in enumerate(block.get("transactions", [])):
        sigs = tx.get("transaction", {}).get("signatures", [])
        for sig in sigs:
            if sig in signatures:
                out[sig] = idx
    return out


def block_metadata(block: dict, slot: int, leader: str | None) -> dict:
    return {
        "slot": slot,
        "leader": leader,
        "block_time": block.get("blockTime"),
        "block_height": block.get("blockHeight"),
        "tx_count": len(block.get("transactions", [])),
        "parent_slot": block.get("parentSlot"),
    }


def save_raw_block(raw_dir: Path, slot: int, block: dict) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / f"block-{slot}.json"
    path.write_text(json.dumps(block))
    return path


def collect_for_slots(rpc, raw_dir: Path, slots: list[int], our_signatures: set[str], slot_to_leader: dict[int, str]):
    """Poll each slot once available; store raw JSON; return landing records.

    Returns (landings, blocks_meta) where landings maps signature ->
    {slot, index, position_percentile}.
    """
    landings: dict[str, dict] = {}
    blocks_meta: list[dict] = []
    remaining = set(our_signatures)
    for slot in slots:
        if not remaining:
            break
        block = rpc.wait_for_block(slot)
        if block is None:
            blocks_meta.append({"slot": slot, "leader": slot_to_leader.get(slot), "skipped_or_missing": True})
            continue
        save_raw_block(raw_dir, slot, block)
        meta = block_metadata(block, slot, slot_to_leader.get(slot))
        blocks_meta.append(meta)
        positions = extract_positions(block, remaining)
        tx_count = meta["tx_count"]
        for sig, idx in positions.items():
            landings[sig] = {
                "slot": slot,
                "index": idx,
                "position_percentile": (idx / (tx_count - 1)) if tx_count > 1 else 0.0,
                "block_tx_count": tx_count,
                "leader": slot_to_leader.get(slot),
            }
            remaining.discard(sig)
    return landings, blocks_meta

"""Burst planning: controlled-variable assignment, blind to send order.

A burst plan is pure data (JSON-serialisable) built from a recorded seed, so
the exact same assignment can be reconstructed by anyone verifying the run.

Design guarantees enforced here (and covered by unit tests):
- Fee levels are assigned round-robin from a seeded shuffle: balanced across
  the burst, random in which transaction gets which level.
- The send order is a SEPARATE seeded permutation, drawn independently of the
  fee assignment — send sequence carries no information about fee level.
- Actors rotate across the burst (no single fee payer serialises itself).
- A fixed-size subset is marked `shared_sink=True`: those transactions all
  transfer to one common writable sink account (the lock probe).
"""

from __future__ import annotations

import random
import uuid
from dataclasses import asdict, dataclass, field


@dataclass
class PlannedTx:
    tx_index: int  # identity within the burst (0..burst_size-1)
    actor_index: int
    cu_price_micro: int  # assigned fee level
    shared_sink: bool  # part of the shared-writable-account probe subset
    send_seq: int  # position in the actual send order (permutation)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class BurstPlan:
    burst_id: str
    seed: int
    target_leader: str | None
    target_window_start: int | None
    fee_levels: list[int]
    txs: list[PlannedTx] = field(default_factory=list)

    def in_send_order(self) -> list[PlannedTx]:
        return sorted(self.txs, key=lambda t: t.send_seq)

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


def assign_fee_levels(burst_size: int, fee_levels: list[int], rng: random.Random) -> list[int]:
    """Balanced assignment: each level used floor or ceil times, shuffled."""
    reps = [fee_levels[i % len(fee_levels)] for i in range(burst_size)]
    rng.shuffle(reps)
    return reps


def plan_burst(
    seed: int,
    burst_size: int = 12,
    num_actors: int = 4,
    shared_subset_size: int = 4,
    fee_levels: list[int] | None = None,
    target_leader: str | None = None,
    target_window_start: int | None = None,
) -> BurstPlan:
    if fee_levels is None:
        from .config import FEE_LEVELS_MICRO_LAMPORTS

        fee_levels = list(FEE_LEVELS_MICRO_LAMPORTS)
    rng = random.Random(seed)
    fees = assign_fee_levels(burst_size, fee_levels, rng)

    # Which txs form the shared-sink probe subset (random positions).
    indices = list(range(burst_size))
    rng.shuffle(indices)
    shared = set(indices[:shared_subset_size])

    # Send order: independent permutation (separate Random stream, seeded
    # from the same burst seed but drawn after assignment so the two are
    # decorrelated by construction).
    send_perm = list(range(burst_size))
    rng.shuffle(send_perm)
    send_seq_of = {tx_idx: pos for pos, tx_idx in enumerate(send_perm)}

    txs = [
        PlannedTx(
            tx_index=i,
            actor_index=i % num_actors,
            cu_price_micro=fees[i],
            shared_sink=i in shared,
            send_seq=send_seq_of[i],
        )
        for i in range(burst_size)
    ]
    return BurstPlan(
        burst_id=uuid.uuid4().hex[:12],
        seed=seed,
        target_leader=target_leader,
        target_window_start=target_window_start,
        fee_levels=list(fee_levels),
        txs=txs,
    )

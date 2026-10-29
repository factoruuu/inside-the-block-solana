"""Leader schedule handling and window watching."""

from __future__ import annotations

import time
from dataclasses import dataclass

SLOTS_PER_WINDOW = 4


def invert_schedule(schedule: dict[str, list[int]], epoch_start_slot: int = 0) -> dict[int, str]:
    """getLeaderSchedule returns {leader_pubkey: [slots]} where slot indices
    are RELATIVE to the first slot of the epoch (verified live: a current-
    epoch response spans 0..431999). Pass the epoch's absolute first slot to
    get an absolute slot->leader map."""
    return {
        int(slot) + epoch_start_slot: leader
        for leader, slots in schedule.items()
        for slot in slots
    }


def epoch_start_slot(epoch_info: dict) -> int:
    """Absolute first slot of the current epoch, from getEpochInfo."""
    return int(epoch_info["absoluteSlot"]) - int(epoch_info["slotIndex"])


def slot_to_leader_map(rpc, slot: int | None = None) -> dict[int, str]:
    """Absolute slot->leader map for the epoch containing `slot` (default:
    the current epoch)."""
    info = rpc.get_epoch_info()
    schedule = rpc.get_leader_schedule(slot)
    return invert_schedule(schedule, epoch_start_slot(info))


@dataclass(frozen=True)
class LeaderWindow:
    leader_node_pubkey: str
    start_slot: int

    @property
    def slots(self) -> list[int]:
        return [self.start_slot + i for i in range(SLOTS_PER_WINDOW)]

    @property
    def end_slot(self) -> int:
        return self.start_slot + SLOTS_PER_WINDOW - 1


def find_windows(slot_to_leader: dict[int, str], leader_pubkey: str, after_slot: int) -> list[LeaderWindow]:
    """All 4-slot windows for a leader starting at or after `after_slot`."""
    starts = [
        s
        for s in sorted(slot_to_leader)
        if s >= after_slot
        and slot_to_leader.get(s) == leader_pubkey
        and all(slot_to_leader.get(s + i) == leader_pubkey for i in range(SLOTS_PER_WINDOW))
        and (s % SLOTS_PER_WINDOW == 0)
    ]
    return [LeaderWindow(leader_node_pubkey=leader_pubkey, start_slot=s) for s in starts]


def sleep_until_slot(rpc, target_slot: int, poll_s: float = 0.1) -> int:
    """Poll getSlot until the chain reaches target_slot; returns observed slot.

    Post-Alpenglow slot time is ~400ms, so we poll instead of trusting
    wall-clock estimates.
    """
    while True:
        current = rpc.get_slot()
        if current >= target_slot:
            return current
        # Sleep roughly the remaining slots, capped to stay responsive.
        remaining = target_slot - current
        time.sleep(min(poll_s + 0.35 * max(remaining - 1, 0), 2.0))

"""Persistent spend ledger with a hard cap.

Only transactions that were ACTUALLY SENT (RPC returned a signature) are
recorded. Planning and simulation never touch the ledger. The ledger survives
restarts so the cap holds across an entire measurement campaign, and every
send is pre-checked: if the estimated fee of the next transaction would push
the recorded total over the cap, the send is refused before it happens.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path


class SpendCapExceeded(Exception):
    """Raised when a send would breach the spend cap. Treat as a hard abort."""


@dataclass
class SpendLedger:
    cap_lamports: int
    path: Path | None = None
    entries: list[dict] = field(default_factory=list)

    # -- persistence -------------------------------------------------------
    @classmethod
    def load(cls, path: Path, cap_lamports: int) -> "SpendLedger":
        if path.exists():
            data = json.loads(path.read_text())
            if data.get("cap_lamports") != cap_lamports:
                raise ValueError(
                    f"Ledger cap {data.get('cap_lamports')} != configured cap {cap_lamports}; "
                    "refusing to continue a campaign under a different cap."
                )
            return cls(cap_lamports=cap_lamports, path=path, entries=data.get("entries", []))
        return cls(cap_lamports=cap_lamports, path=path)

    def save(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"cap_lamports": self.cap_lamports, "entries": self.entries}
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2))
        tmp.replace(self.path)

    # -- accounting --------------------------------------------------------
    @property
    def spent_lamports(self) -> int:
        return sum(int(e["fee_lamports"]) for e in self.entries)

    @property
    def remaining_lamports(self) -> int:
        return self.cap_lamports - self.spent_lamports

    def check_can_spend(self, estimated_fee_lamports: int) -> None:
        """Pre-send gate. Raises SpendCapExceeded if this send breaches the cap."""
        if self.spent_lamports + estimated_fee_lamports > self.cap_lamports:
            raise SpendCapExceeded(
                f"Spend cap would be breached: spent={self.spent_lamports} "
                f"+ next~{estimated_fee_lamports} > cap={self.cap_lamports} lamports."
            )

    def record_sent(self, signature: str, fee_lamports: int, burst_id: str) -> None:
        """Record a transaction that was actually sent (signature known)."""
        self.entries.append(
            {
                "signature": signature,
                "fee_lamports": int(fee_lamports),
                "burst_id": burst_id,
                "recorded_at_unix": time.time(),
            }
        )
        self.save()

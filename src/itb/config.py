"""Configuration from environment variables only.

Keys are loaded from KEYPAIR_DIR at send time and never written anywhere by
this package. No secret ever comes from a CLI argument.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_SPEND_CAP_LAMPORTS = 50_000_000  # 0.05 SOL — the brief's fee budget.

# CU price levels (micro-lamports per compute unit). CU limit is fixed for all
# transactions, so ordering by price == ordering by total priority fee.
FEE_LEVELS_MICRO_LAMPORTS = [0, 1_000, 10_000, 50_000, 250_000]
CU_LIMIT = 30_000  # measured: memo ix alone meters ~19,083 CUs in simulation
# (BPF program execution); + transfer + 2 compute-budget ixs ~= 19.5k total.
# 30k gives ~50% headroom. The limit is FIXED for every tx, so priority-fee
# ordering across txs is still exactly CU-price ordering. (Was 1_200 in the
# first live attempt — every send failed preflight with ProgramFailedToComplete;
# see README "What went wrong".)
BASE_FEE_LAMPORTS_PER_SIGNATURE = 5_000


def priority_fee_lamports(cu_price_micro: int, cu_limit: int = CU_LIMIT) -> int:
    """Priority fee = ceil(CU limit * price / 1e6), as the runtime charges it."""
    return -(-cu_limit * cu_price_micro // 1_000_000)


def estimated_fee_lamports(cu_price_micro: int, cu_limit: int = CU_LIMIT) -> int:
    return BASE_FEE_LAMPORTS_PER_SIGNATURE + priority_fee_lamports(cu_price_micro, cu_limit)


@dataclass(frozen=True)
class Config:
    rpc_url: str = "https://api.mainnet-beta.solana.com"
    send_rpc_url: str | None = None  # defaults to rpc_url
    cluster: str | None = None  # must be set for live runs
    keypair_dir: Path = Path("keys")
    spend_cap_lamports: int = DEFAULT_SPEND_CAP_LAMPORTS
    data_dir: Path = Path("data")
    num_actors: int = 4
    burst_size: int = 12
    shared_subset_size: int = 4
    bursts_per_validator: int = 20
    min_validators: int = 6
    min_client_classes: int = 3
    lead_slots: int = 12  # start sending this many slots before the window.
    # Measured live (2026-10-29): a 12-tx burst's send span is ~4 s (~10
    # slots; every sendTransaction runs a preflight simulation) plus up to
    # ~3 s of RPC latency/backoff — with the original 2-slot lead the burst
    # started only as its 4-slot (1.6 s) target window was already ending.
    # 12 slots (~4.8 s) puts the burst in flight as the window opens.
    fee_levels: tuple[int, ...] = field(default_factory=lambda: tuple(FEE_LEVELS_MICRO_LAMPORTS))

    @property
    def send_url(self) -> str:
        return self.send_rpc_url or self.rpc_url

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def analysis_dir(self) -> Path:
        return self.data_dir / "analysis"

    @property
    def ledger_path(self) -> Path:
        return self.data_dir / "spend-ledger.json"

    @classmethod
    def from_env(cls, **overrides) -> "Config":
        env = os.environ
        values = dict(
            rpc_url=env.get("RPC_URL", cls.rpc_url),
            send_rpc_url=env.get("SEND_RPC_URL") or None,
            cluster=env.get("CLUSTER") or None,
            keypair_dir=Path(env.get("KEYPAIR_DIR", str(cls.keypair_dir))),
            spend_cap_lamports=int(env.get("SPEND_CAP_LAMPORTS", cls.spend_cap_lamports)),
            data_dir=Path(env.get("DATA_DIR", str(cls.data_dir))),
        )
        values.update(overrides)
        return cls(**values)


def require_live_allowed(cfg: Config, live_flag: bool) -> None:
    """Gate for real sending: explicit --live flag AND a named cluster."""
    if not live_flag:
        raise SystemExit("Refusing to send: pass --live to enable live sending.")
    if not cfg.cluster:
        raise SystemExit("Refusing to send: set the CLUSTER env var (e.g. mainnet-beta or devnet).")

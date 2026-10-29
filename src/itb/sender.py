"""Burst sending with spend-cap enforcement and full per-tx records."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass

from solders.keypair import Keypair

from .burst import BurstPlan
from .config import Config, estimated_fee_lamports
from .ledger import SpendCapExceeded, SpendLedger
from .rpc import RpcClient
from .txbuild import build_tx, encode_tx


@dataclass
class SentTxRecord:
    burst_id: str
    tx_index: int
    actor_index: int
    actor_pubkey: str
    cu_price_micro: int
    estimated_fee_lamports: int
    shared_sink: bool
    send_seq: int
    signature: str | None  # None if the send itself failed
    send_error: str | None
    send_timestamp_unix: float | None
    send_timestamp_monotonic: float | None
    target_leader: str | None
    target_window_start: int | None
    observed_slot_before_burst: int | None

    def to_dict(self) -> dict:
        return asdict(self)


def send_burst(
    cfg: Config,
    send_rpc: RpcClient,
    plan: BurstPlan,
    actors: list[Keypair],
    blockhash: str,
    ledger: SpendLedger,
    observed_slot_before_burst: int | None,
) -> list[SentTxRecord]:
    """Send one planned burst in its planned send order.

    Every send is pre-checked against the spend ledger; SpendCapExceeded
    aborts the whole run (hard stop, not a per-tx skip) so a campaign can
    never drift over budget. A failed send RPC call is recorded with its
    error and NOT charged to the ledger (no signature == not sent).
    """
    records: list[SentTxRecord] = []
    for planned in plan.in_send_order():
        fee = estimated_fee_lamports(planned.cu_price_micro)
        ledger.check_can_spend(fee)  # raises SpendCapExceeded -> hard abort
        actor = actors[planned.actor_index]
        tx = build_tx(
            actor=actor,
            cu_price_micro=planned.cu_price_micro,
            use_shared_sink=planned.shared_sink,
            blockhash=blockhash,
            memo_nonce=f"itb:{plan.burst_id}:{planned.tx_index}",
        )
        encoded = encode_tx(tx)
        ts_unix = ts_mono = None
        signature = None
        error = None
        try:
            ts_mono = time.monotonic()
            ts_unix = time.time()
            signature = send_rpc.send_transaction(encoded)
        except Exception as exc:  # recorded, not charged
            error = str(exc)
        rec = SentTxRecord(
            burst_id=plan.burst_id,
            tx_index=planned.tx_index,
            actor_index=planned.actor_index,
            actor_pubkey=str(actor.pubkey()),
            cu_price_micro=planned.cu_price_micro,
            estimated_fee_lamports=fee,
            shared_sink=planned.shared_sink,
            send_seq=planned.send_seq,
            signature=signature,
            send_error=error,
            send_timestamp_unix=ts_unix,
            send_timestamp_monotonic=ts_mono,
            target_leader=plan.target_leader,
            target_window_start=plan.target_window_start,
            observed_slot_before_burst=observed_slot_before_burst,
        )
        records.append(rec)
        if signature is not None:
            ledger.record_sent(signature, fee, plan.burst_id)
    return records

"""Transaction construction with solders.

Every measurement transaction has the same shape:
  1. ComputeBudget: SetComputeUnitLimit (fixed CU_LIMIT for all txs)
  2. ComputeBudget: SetComputeUnitPrice (the experimental variable)
  3. Memo: unique per-transaction nonce string (prevents signature collisions
     between otherwise-identical txs from the same actor under one blockhash)
  4. SystemProgram: transfer 1 lamport
     - baseline: actor -> itself (self-transfer; the tx write-locks ONLY the
       actor's own account, so baseline txs of different actors share no
       writable account at all)
     - probe subset: actor -> the single SHARED sink account (one common
       writable account across all actors — the lock-contention probe)

Sink design note (live-run fix, 2026-10-29): the original design transferred
to *fresh derived* sink addresses. Current mainnet rejects creating an
account below the rent-exempt minimum (InsufficientFundsForRent), so a
1-lamport transfer to a non-existent sink always fails preflight. Baseline
therefore self-transfers, and the shared sink is one real, operator-funded,
rent-exempt account (SHARED_SINK below; its keypair is an operator key kept
with the actor keys, outside this repo).

Transaction signing/serialisation is delegated to solders — hand-rolling the
wire format is a classic source of silent measurement bugs.
"""

from __future__ import annotations

import base64
from pathlib import Path

from solders.compute_budget import set_compute_unit_limit, set_compute_unit_price
from solders.hash import Hash
from solders.instruction import AccountMeta, Instruction
from solders.keypair import Keypair
from solders.message import Message
from solders.pubkey import Pubkey
from solders.system_program import TransferParams, transfer
from solders.transaction import Transaction

from .config import CU_LIMIT

TRANSFER_LAMPORTS = 1

MEMO_PROGRAM_ID = Pubkey.from_string("MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr")


def memo_instruction(signer: Pubkey, memo: bytes) -> Instruction:
    """SPL Memo instruction (built by hand — solders has no memo helper).
    The signer account is read-only in the memo program."""
    return Instruction(
        MEMO_PROGRAM_ID,
        memo,
        [AccountMeta(signer, is_signer=True, is_writable=False)],
    )


def load_keypairs(keypair_dir: Path, prefix: str, count: int) -> list[Keypair]:
    """Load keypairs named <prefix>-<i>.json (Solana CLI JSON byte-array format)
    from the keypair directory. Files are read-only inputs; never written."""
    kps: list[Keypair] = []
    for i in range(count):
        path = keypair_dir / f"{prefix}-{i}.json"
        if not path.exists():
            raise FileNotFoundError(f"Missing keypair file: {path}")
        kps.append(Keypair.from_bytes(bytes(__import__("json").loads(path.read_text()))))
    return kps


# The shared sink for the lock-probe subset: ONE real account, funded
# rent-exempt by the operator before the campaign, so every actor's probe tx
# can transfer 1 lamport to it (and thereby write-lock it). Its keypair is an
# operator key held outside this repo; the pubkey is a constant so plans and
# data are reproducible across runs and machines.
SHARED_SINK = Pubkey.from_string("ApvAAkQZKnjYmuV7gbfea7YGRLCQZVsd7vAVQmMxMwDP")


def shared_sink() -> Pubkey:
    """The shared sink pubkey for the probe subset (see SHARED_SINK)."""
    return SHARED_SINK


def build_tx(
    actor: Keypair,
    cu_price_micro: int,
    use_shared_sink: bool,
    blockhash: str,
    memo_nonce: str,
) -> Transaction:
    # Probe txs transfer to the shared sink; baseline txs self-transfer so
    # they write-lock only the actor's own (payer) account.
    sink = shared_sink() if use_shared_sink else actor.pubkey()
    ixs = [
        set_compute_unit_limit(CU_LIMIT),
        set_compute_unit_price(cu_price_micro),
        memo_instruction(actor.pubkey(), memo_nonce.encode()),
        transfer(
            TransferParams(
                from_pubkey=actor.pubkey(),
                to_pubkey=sink,
                lamports=TRANSFER_LAMPORTS,
            )
        ),
    ]
    msg = Message(ixs, actor.pubkey())
    return Transaction([actor], msg, Hash.from_string(blockhash))


def encode_tx(tx: Transaction) -> str:
    return base64.b64encode(bytes(tx)).decode()

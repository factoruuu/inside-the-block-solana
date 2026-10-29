"""Validator selection and client classification.

PRIMARY signal: the `clientId` field of getClusterNodes. Current Agave RPCs
resolve the node's self-declared client ID to a name (observed live on
mainnet, 2026-10-29: Agave, JitoLabs, AgaveBam, Firedancer, Frankendancer,
HarmonicAgave, HarmonicFiredancer, FireBAM, Rakurai, Raiku, Unknown(n)).
This matters because version strings alone NO LONGER identify the client:
on live mainnet, stock Agave, Jito and AgaveBam nodes all report the same
version strings (e.g. 4.3.2), and Firedancer reports both 26.10.x and 0.1.1.

FALLBACK (older RPCs without clientId): version-string heuristics —
- contains "jito"                       -> jito
- "0.x.y" with >= 3 numeric components  -> frankendancer/firedancer family
- "X.Y.Z" with X >= 1                   -> agave
- anything else                         -> unknown

Both signals are self-reported by the node; classification is therefore
heuristic and is disclosed as such in the report. validators.app data can be
cross-referenced where available.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# clientId name (as resolved by the RPC) -> our class label.
CLIENT_ID_LABELS = {
    "agave": "agave",
    "jitolabs": "jito",
    "agavebam": "agave-bam",
    "firedancer": "firedancer",
    "frankendancer": "frankendancer",
    "harmonicagave": "harmonic-agave",
    "harmonicfiredancer": "harmonic-firedancer",
    "firebam": "firebam",
    "rakurai": "rakurai",
    "raiku": "raiku",
}


def classify_client(version: str | None, client_id: str | None = None) -> str:
    if client_id:
        key = client_id.strip().lower()
        if key in CLIENT_ID_LABELS:
            return CLIENT_ID_LABELS[key]
        if not key.startswith("unknown"):
            return key  # a named client we have not mapped: keep its name
    if not version:
        return "unknown"
    v = version.strip().lower()
    if "jito" in v:
        return "jito"
    if "frankendancer" in v:
        return "frankendancer"
    if "firedancer" in v:
        return "firedancer"
    parts = re.findall(r"\d+", v)
    if len(parts) >= 3 and parts[0] == "0":
        return "frankendancer/firedancer"
    if parts and int(parts[0]) >= 1:
        return "agave"
    return "unknown"


@dataclass
class ValidatorInfo:
    vote_pubkey: str
    node_pubkey: str
    activated_stake: int
    version: str | None
    client: str
    client_id: str | None = None
    gossip: str | None = None

    def to_dict(self) -> dict:
        return {
            "vote_pubkey": self.vote_pubkey,
            "node_pubkey": self.node_pubkey,
            "activated_stake": self.activated_stake,
            "version": self.version,
            "client": self.client,
            "client_id": self.client_id,
            "gossip": self.gossip,
        }


def join_validators(vote_accounts: dict, cluster_nodes: list[dict]) -> list[ValidatorInfo]:
    nodes = {n["pubkey"]: n for n in cluster_nodes}
    out: list[ValidatorInfo] = []
    for entry in vote_accounts.get("current", []):
        node = nodes.get(entry["nodePubkey"], {})
        version = node.get("version")
        client_id = node.get("clientId")
        out.append(
            ValidatorInfo(
                vote_pubkey=entry["votePubkey"],
                node_pubkey=entry["nodePubkey"],
                activated_stake=int(entry.get("activatedStake", 0)),
                version=version,
                client=classify_client(version, client_id),
                client_id=client_id,
                gossip=node.get("gossip"),
            )
        )
    return out


def select_validators(
    validators: list[ValidatorInfo],
    min_validators: int = 6,
    min_client_classes: int = 3,
    per_class: int = 2,
    target_validators: int = 8,
) -> list[ValidatorInfo]:
    """Deterministic selection. Client classes are taken in descending
    total-stake order, per_class highest-stake validators from each, until
    both minimums are met and the target size is reached. This keeps the
    campaign focused on the clients that actually produce most blocks while
    guaranteeing the brief's >=6 validators / >=3 classes. Raises if the live
    cluster cannot satisfy the minimums."""
    by_client: dict[str, list[ValidatorInfo]] = {}
    for v in validators:
        if v.client != "unknown":
            by_client.setdefault(v.client, []).append(v)
    classes = [c for c, lst in by_client.items() if lst]
    if len(classes) < min_client_classes:
        raise ValueError(
            f"Only {len(classes)} identifiable client classes on this cluster "
            f"({sorted(classes)}); brief requires >= {min_client_classes}."
        )
    for lst in by_client.values():
        lst.sort(key=lambda v: (-v.activated_stake, v.vote_pubkey))
    classes.sort(key=lambda c: (-sum(v.activated_stake for v in by_client[c]), c))
    selected: list[ValidatorInfo] = []
    classes_used = 0
    for client in classes:
        if len(selected) >= target_validators and classes_used >= min_client_classes:
            break
        selected.extend(by_client[client][:per_class])
        classes_used += 1
    # Top up by stake if still short of the validator minimum.
    if len(selected) < min_validators:
        chosen = {v.vote_pubkey for v in selected}
        rest = sorted(
            (v for v in validators if v.vote_pubkey not in chosen and v.client != "unknown"),
            key=lambda v: (-v.activated_stake, v.vote_pubkey),
        )
        selected.extend(rest[: min_validators - len(selected)])
    if len(selected) < min_validators or classes_used < min_client_classes:
        raise ValueError(
            f"Selection failed: {len(selected)} validators across {classes_used} classes; "
            f"brief requires >= {min_validators} / >= {min_client_classes}."
        )
    selected.sort(key=lambda v: (-v.activated_stake, v.vote_pubkey))
    return selected

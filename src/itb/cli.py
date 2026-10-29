"""CLI: itb plan | run | analyze | init-keys | fund-devnet

- plan (DEFAULT, dry-run): resolve validators + upcoming windows, build the
  burst plans, simulate the transactions, send NOTHING, touch no ledger.
- run: live sending. Requires --live AND the CLUSTER env var. Enforces the
  spend cap via the persistent ledger on every transaction.
- analyze: offline; reads data/raw + data/analysis inputs, writes stats.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from . import analyze as analyze_mod
from .burst import plan_burst
from .collector import collect_for_slots
from .config import Config, require_live_allowed
from .leader import find_windows, slot_to_leader_map, sleep_until_slot
from .ledger import SpendCapExceeded, SpendLedger
from .rpc import RpcClient
from .sender import send_burst
from .txbuild import encode_tx, build_tx, load_keypairs
from .validators import join_validators, select_validators


def _append_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


def _resolve_validators(cfg: Config, rpc: RpcClient) -> list:
    validators = join_validators(rpc.get_vote_accounts(), rpc.get_cluster_nodes())
    selected = select_validators(validators, cfg.min_validators, cfg.min_client_classes)
    cfg.analysis_dir.mkdir(parents=True, exist_ok=True)
    (cfg.analysis_dir / "validators.json").write_text(
        json.dumps([v.to_dict() for v in selected], indent=2)
    )
    return selected


def cmd_plan(cfg: Config, args) -> int:
    rpc = RpcClient(cfg.rpc_url)
    selected = _resolve_validators(cfg, rpc)
    print(f"Selected {len(selected)} validators:")
    for v in selected:
        print(f"  {v.node_pubkey}  client={v.client}  version={v.version}  stake={v.activated_stake}")
    current = rpc.get_slot()
    schedule = slot_to_leader_map(rpc, current)
    blockhash = rpc.get_latest_blockhash()
    # Dry-run: build + simulate one burst for the first validator with a window.
    actors = _load_actors_if_present(cfg)
    for v in selected:
        windows = find_windows(schedule, v.node_pubkey, current + 10)
        if not windows:
            print(f"No upcoming window found for {v.node_pubkey} in this epoch schedule slice.")
            continue
        w = windows[0]
        plan = plan_burst(
            seed=int(time.time()) % 100000,
            burst_size=cfg.burst_size,
            num_actors=cfg.num_actors,
            shared_subset_size=cfg.shared_subset_size,
            fee_levels=list(cfg.fee_levels),
            target_leader=v.node_pubkey,
            target_window_start=w.start_slot,
        )
        print(f"\nValidator {v.node_pubkey}: next window starts slot {w.start_slot} (slots {w.slots})")
        print(f"Burst plan {plan.burst_id} (seed {plan.seed}):")
        for t in plan.in_send_order():
            print(
                f"  send_seq={t.send_seq:2d} tx={t.tx_index:2d} actor={t.actor_index} "
                f"cu_price={t.cu_price_micro:>7} shared_sink={t.shared_sink}"
            )
        if actors:
            tx = build_tx(actors[0], plan.txs[0].cu_price_micro, plan.txs[0].shared_sink,
                          blockhash, f"itb:{plan.burst_id}:0")
            sim = rpc.simulate_transaction(encode_tx(tx))
            err = sim.get("value", {}).get("err")
            print(f"Simulation of first tx: err={err} (plan mode sends NOTHING)")
        break
    print("\nPLAN MODE: no transactions sent, ledger untouched.")
    return 0


def _load_actors_if_present(cfg: Config):
    try:
        return load_keypairs(cfg.keypair_dir, "actor", cfg.num_actors)
    except FileNotFoundError:
        return None


def cmd_run(cfg: Config, args) -> int:
    require_live_allowed(cfg, args.live)
    rpc = RpcClient(cfg.rpc_url)
    send_rpc = RpcClient(cfg.send_url)
    actors = load_keypairs(cfg.keypair_dir, "actor", cfg.num_actors)
    ledger = SpendLedger.load(cfg.ledger_path, cfg.spend_cap_lamports)
    print(f"Spend ledger: spent={ledger.spent_lamports} / cap={ledger.cap_lamports} lamports")

    send_records_path = cfg.raw_dir / "send-records.jsonl"
    landings_path = cfg.raw_dir / "landings.json"
    landings: dict = json.loads(landings_path.read_text()) if landings_path.exists() else {}

    bursts_done = 0
    max_bursts = args.max_bursts

    def do_burst(target_leader: str | None, window_start: int | None) -> None:
        nonlocal bursts_done
        seed = (int(time.time()) % 1_000_000) + bursts_done * 7919
        plan = plan_burst(
            seed=seed,
            burst_size=cfg.burst_size,
            num_actors=cfg.num_actors,
            shared_subset_size=cfg.shared_subset_size,
            fee_levels=list(cfg.fee_levels),
            target_leader=target_leader,
            target_window_start=window_start,
        )
        blockhash = rpc.get_latest_blockhash()
        observed = rpc.get_slot()
        records = send_burst(cfg, send_rpc, plan, actors, blockhash, ledger, observed)
        _append_jsonl(send_records_path, [r.to_dict() for r in records])
        sigs = {r.signature for r in records if r.signature}
        # Collect from the moment firing started (lead_slots before the
        # window) plus the window and a tail — landings before the window
        # start are real (the burst is sent across the lead) and are
        # labelled with their actual leader.
        first = window_start if window_start is not None else observed
        collect_from = first - (cfg.lead_slots if window_start is not None else 0)
        slots = list(range(collect_from, first + 16))
        schedule = slot_to_leader_map(rpc, first)
        new_landings, blocks_meta = collect_for_slots(rpc, cfg.raw_dir, slots, sigs, schedule)
        landings.update(new_landings)
        landings_path.write_text(json.dumps(landings, indent=2))
        _append_jsonl(cfg.raw_dir / "blocks.jsonl", blocks_meta)
        landed_here = sum(1 for r in records if r.signature in new_landings)
        print(
            f"Burst {plan.burst_id}: sent {len(sigs)}/{len(records)}, landed in collection window "
            f"{landed_here}. Ledger spent={ledger.spent_lamports} lamports."
        )
        bursts_done += 1

    try:
        if args.any_leader:
            while bursts_done < max_bursts:
                current = rpc.get_slot()
                target = current + 3
                sleep_until_slot(rpc, target)
                do_burst(None, target)
        else:
            selected = _resolve_validators(cfg, rpc)
            remaining = {v.node_pubkey: cfg.bursts_per_validator for v in selected}
            while bursts_done < max_bursts and any(n > 0 for n in remaining.values()):
                current = rpc.get_slot()
                schedule = slot_to_leader_map(rpc, current)
                progressed = False
                for v in selected:
                    if remaining[v.node_pubkey] <= 0 or bursts_done >= max_bursts:
                        continue
                    # Refresh the slot per validator: a burst's send+collect
                    # can take minutes under RPC rate limiting, and with the
                    # iteration-start slot the later validators' "next
                    # windows" were already in the past when fired — the
                    # burst then missed its target window entirely (first
                    # campaign, 2026-10-29: most bursts landed 100-900 slots
                    # after their target windows). The schedule map covers
                    # the whole epoch, so only `current` needs refreshing.
                    current = rpc.get_slot()
                    windows = find_windows(schedule, v.node_pubkey, current + cfg.lead_slots + 1)
                    if not windows:
                        continue
                    w = windows[0]
                    sleep_until_slot(rpc, max(current, w.start_slot - cfg.lead_slots))
                    do_burst(v.node_pubkey, w.start_slot)
                    remaining[v.node_pubkey] -= 1
                    progressed = True
                if not progressed:
                    print("No further windows for selected validators in this epoch slice; stopping.")
                    break
    except SpendCapExceeded as exc:
        print(f"HARD ABORT — {exc}", file=sys.stderr)
        print(f"Final ledger: spent={ledger.spent_lamports} / cap={ledger.cap_lamports} lamports")
        return 2
    print(f"Done. {bursts_done} bursts. Ledger spent={ledger.spent_lamports} lamports.")
    return 0


def cmd_analyze(cfg: Config, args) -> int:
    result = analyze_mod.analyze(cfg.data_dir)
    lr = result["overall"]["landing_rate"]
    print(f"Sent {lr['sent']}, landed {lr['landed']} (rate {lr['rate']}).")
    print(f"Wrote {cfg.analysis_dir}/stats.json, joined-rows.csv, summary.md")
    return 0


def cmd_init_keys(cfg: Config, args) -> int:
    """Generate throwaway/operator actor keypairs into KEYPAIR_DIR.

    Refuses to overwrite existing files. These are LOCAL operator keys; the
    directory is gitignored and keys must be funded out-of-band (devnet
    airdrop, or a small mainnet transfer by the operator).
    """
    from solders.keypair import Keypair

    cfg.keypair_dir.mkdir(parents=True, exist_ok=True)
    for i in range(cfg.num_actors):
        path = cfg.keypair_dir / f"actor-{i}.json"
        if path.exists():
            print(f"exists, skipping: {path}")
            continue
        kp = Keypair()
        path.write_text(json.dumps(list(bytes(kp))))
        print(f"wrote {path}  pubkey={kp.pubkey()}")
    sink_note = cfg.keypair_dir / "README.keys"
    sink_note.write_text(
        "Actor keypairs live here. This directory is gitignored. "
        "Never commit or share these files.\n"
    )
    return 0


def cmd_fund_devnet(cfg: Config, args) -> int:
    if cfg.cluster not in {"devnet", "testnet"}:
        raise SystemExit("fund-devnet only works with CLUSTER=devnet or testnet.")
    rpc = RpcClient(cfg.rpc_url)
    actors = load_keypairs(cfg.keypair_dir, "actor", cfg.num_actors)
    for kp in actors:
        pub = str(kp.pubkey())
        bal = rpc.get_balance(pub)
        print(f"{pub}: balance {bal}")
        if bal < args.min_lamports:
            try:
                sig = rpc.request_airdrop(pub, 1_000_000_000)
                print(f"  airdrop requested: {sig}")
            except Exception as exc:
                print(f"  airdrop FAILED: {exc}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="itb", description="Inside the Block measurement CLI")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("plan", help="dry-run (default): resolve, plan, simulate; send nothing")
    p_run = sub.add_parser("run", help="live sending (requires --live and CLUSTER env)")
    p_run.add_argument("--live", action="store_true", help="explicitly enable live sending")
    p_run.add_argument("--max-bursts", type=int, default=10_000, help="safety bound on bursts this invocation")
    p_run.add_argument("--any-leader", action="store_true",
                       help="debug/smoke mode: burst at upcoming slots regardless of leader")
    sub.add_parser("analyze", help="offline analysis of collected data")
    sub.add_parser("init-keys", help="generate actor keypairs into KEYPAIR_DIR (never overwrites)")
    p_fund = sub.add_parser("fund-devnet", help="request devnet/testnet airdrops for actors")
    p_fund.add_argument("--min-lamports", type=int, default=100_000_000)
    args = parser.parse_args(argv)
    cfg = Config.from_env()
    command = args.command or "plan"
    if command == "plan":
        return cmd_plan(cfg, args)
    if command == "run":
        return cmd_run(cfg, args)
    if command == "analyze":
        return cmd_analyze(cfg, args)
    if command == "init-keys":
        return cmd_init_keys(cfg, args)
    if command == "fund-devnet":
        return cmd_fund_devnet(cfg, args)
    parser.error(f"unknown command {command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

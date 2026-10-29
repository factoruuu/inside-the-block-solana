"""Analyzer: join send records with landing positions; compute per-validator
and per-client ordering statistics; emit CSV/JSON + a markdown summary.

Inputs (all under data/):
- data/raw/send-records.jsonl        one JSON object per sent transaction
- data/raw/landings.json             signature -> landing info (from collector)
- data/analysis/validators.json      selected validators with client labels
- data/analysis/leader-clients.json  OPTIONAL: client/version for any other
                                     leader (spillover blocks), same shape;
                                     validators.json wins on conflicts
- data/raw/blocks.jsonl              block metadata per touched slot

The analyzer reads ONLY these files (never the network), so judges can
re-run it on the published raw data and reproduce every number.
"""

from __future__ import annotations

import csv
import io
import json
from collections import defaultdict
from pathlib import Path

from .stats import bootstrap_ci_fraction, mean, pairwise_concordance, spearman


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def build_joined_rows(send_records: list[dict], landings: dict[str, dict]) -> list[dict]:
    rows = []
    for rec in send_records:
        row = dict(rec)
        land = landings.get(rec.get("signature") or "")
        row["landed"] = land is not None
        if land:
            row.update(
                {
                    "landed_slot": land["slot"],
                    "block_index": land["index"],
                    "position_percentile": land["position_percentile"],
                    "actual_leader": land.get("leader"),
                    "block_tx_count": land.get("block_tx_count"),
                }
            )
        rows.append(row)
    return rows


def _same_block_pairs(rows: list[dict]) -> dict[tuple, list[dict]]:
    by_block: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        if r.get("landed"):
            by_block[(r["landed_slot"],)].append(r)
    return by_block


def ordering_stats(rows: list[dict]) -> dict:
    """Fee/send-order concordance over pairs of our txs in the SAME block.

    Outcome value is -block_index so 'higher hypothesis value, earlier
    landing' counts as agreement in pairwise_concordance terms when paired
    with fee; for send order we pair (-send_seq, -block_index).
    """
    blocks = _same_block_pairs(rows)
    fee_pairs: list[tuple[float, float]] = []
    send_pairs: list[tuple[float, float]] = []
    shared_rows: list[dict] = []
    indep_rows: list[dict] = []
    for block_rows in blocks.values():
        for r in block_rows:
            fee_pairs.append((float(r["cu_price_micro"]), float(-r["block_index"])))
            send_pairs.append((float(-r["send_seq"]), float(-r["block_index"])))
            (shared_rows if r.get("shared_sink") else indep_rows).append(r)
    fee_c = pairwise_concordance([p[0] for p in fee_pairs], [p[1] for p in fee_pairs])
    send_c = pairwise_concordance([p[0] for p in send_pairs], [p[1] for p in send_pairs])
    landed = [r for r in rows if r.get("landed")]
    sp = spearman(
        [float(r["cu_price_micro"]) for r in landed],
        [float(r["block_index"]) for r in landed],
    )
    return {
        "same_block_tx_count": len(landed),
        "fee_concordance": fee_c,
        "fee_concordance_ci95": bootstrap_ci_fraction(fee_pairs),
        "send_order_concordance": send_c,
        "send_order_concordance_ci95": bootstrap_ci_fraction(send_pairs),
        "spearman_fee_vs_index": sp,
        "mean_percentile_by_fee": {
            str(level): mean([r["position_percentile"] for r in landed if r["cu_price_micro"] == level])
            for level in sorted({r["cu_price_micro"] for r in landed})
        },
        "shared_sink": {
            "count": len(shared_rows),
            "mean_percentile": mean([r["position_percentile"] for r in shared_rows]),
        },
        "independent": {
            "count": len(indep_rows),
            "mean_percentile": mean([r["position_percentile"] for r in indep_rows]),
        },
    }


def landing_rate(rows: list[dict]) -> dict:
    total = len(rows)
    landed = sum(1 for r in rows if r.get("landed"))
    by_fee: dict[str, dict] = {}
    for level in sorted({r["cu_price_micro"] for r in rows}):
        sub = [r for r in rows if r["cu_price_micro"] == level]
        by_fee[str(level)] = {
            "sent": len(sub),
            "landed": sum(1 for r in sub if r.get("landed")),
        }
    return {"sent": total, "landed": landed, "rate": (landed / total) if total else None, "by_fee_level": by_fee}


def analyze(data_dir: Path) -> dict:
    raw_dir = data_dir / "raw"
    analysis_dir = data_dir / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)

    send_records = _load_jsonl(raw_dir / "send-records.jsonl")
    landings = {}
    if (raw_dir / "landings.json").exists():
        landings = json.loads((raw_dir / "landings.json").read_text())
    validators_info: dict[str, dict] = {}
    if (analysis_dir / "validators.json").exists():
        for v in json.loads((analysis_dir / "validators.json").read_text()):
            validators_info[v["node_pubkey"]] = v
    # Optional enrichment: burst spillover lands in blocks of leaders that
    # were never selected targets. Their client class is still resolvable
    # from cluster data captured at measurement time (leader-clients.json);
    # selected validators (validators.json) take precedence.
    leader_clients_path = analysis_dir / "leader-clients.json"
    if leader_clients_path.exists():
        for pubkey, info in json.loads(leader_clients_path.read_text()).items():
            validators_info.setdefault(pubkey, info)

    rows = build_joined_rows(send_records, landings)

    # Group by ACTUAL leader of the landing block (fallback: target leader
    # for non-landed rows in landing-rate-by-validator).
    by_validator: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        key = r.get("actual_leader") or r.get("target_leader") or "unknown"
        by_validator[key].append(r)

    per_validator = {}
    for leader, vrows in sorted(by_validator.items()):
        info = validators_info.get(leader, {})
        per_validator[leader] = {
            "client": info.get("client", "unknown"),
            "version": info.get("version"),
            "landing_rate": landing_rate(vrows),
            "ordering": ordering_stats([r for r in vrows if r.get("landed")]),
        }

    by_client: dict[str, list[dict]] = defaultdict(list)
    for leader, vrows in by_validator.items():
        client = validators_info.get(leader, {}).get("client", "unknown")
        by_client[client].extend([r for r in vrows if r.get("landed")])
    per_client = {
        client: {"ordering": ordering_stats(crows), "landing_rate": landing_rate(crows)}
        for client, crows in sorted(by_client.items())
    }

    result = {
        "overall": {"landing_rate": landing_rate(rows), "ordering": ordering_stats(rows)},
        "per_validator": per_validator,
        "per_client": per_client,
    }

    (analysis_dir / "stats.json").write_text(json.dumps(result, indent=2, default=str))

    # Joined rows CSV for judges who prefer spreadsheets.
    if rows:
        buf = io.StringIO()
        fields = sorted({k for r in rows for k in r.keys()})
        writer = csv.DictWriter(buf, fieldnames=fields)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)
        (analysis_dir / "joined-rows.csv").write_text(buf.getvalue())

    (analysis_dir / "summary.md").write_text(render_summary(result))
    return result


def _fmt(x, digits=3):
    return "n/a" if x is None else f"{x:.{digits}f}"


def render_summary(result: dict) -> str:
    lines = ["# Analysis summary", ""]
    overall = result["overall"]
    lr = overall["landing_rate"]
    lines.append(f"Sent: {lr['sent']} · Landed: {lr['landed']} · Landing rate: {_fmt(lr['rate'])}")
    lines.append("")
    lines.append("## Overall ordering")
    lines.append(_ordering_block(overall["ordering"]))
    lines.append("## Per-validator")
    for leader, v in result["per_validator"].items():
        lines.append(f"### {leader} (client: {v['client']}, version: {v['version']})")
        vlr = v["landing_rate"]
        lines.append(f"Sent: {vlr['sent']} · Landed: {vlr['landed']} · Rate: {_fmt(vlr['rate'])}")
        lines.append(_ordering_block(v["ordering"]))
    lines.append("## Per-client")
    for client, c in result["per_client"].items():
        lines.append(f"### {client}")
        lines.append(_ordering_block(c["ordering"]))
    lines.append("")
    lines.append(
        "_Interpretation guide: concordance 0.5 = no relationship. Fee concordance clearly above "
        "send-order concordance suggests a fee rule; the reverse suggests arrival-order (FIFO) "
        "behaviour; CIs covering 0.5 mean 'no detectable rule' at this sample size._"
    )
    return "\n".join(lines) + "\n"


def _ordering_block(o: dict) -> str:
    fc = o["fee_concordance"]
    sc = o["send_order_concordance"]
    return (
        f"- Same-block landed txs: {o['same_block_tx_count']}\n"
        f"- Fee concordance: {_fmt(fc['fraction'])} "
        f"(concordant {fc['concordant']}, discordant {fc['discordant']}, tied {fc['tied']}, "
        f"95% CI {_fmt(o['fee_concordance_ci95'][0]) if o['fee_concordance_ci95'] else 'n/a'}–"
        f"{_fmt(o['fee_concordance_ci95'][1]) if o['fee_concordance_ci95'] else 'n/a'})\n"
        f"- Send-order concordance: {_fmt(sc['fraction'])} "
        f"(concordant {sc['concordant']}, discordant {sc['discordant']}, tied {sc['tied']})\n"
        f"- Spearman fee vs block index: {_fmt(o['spearman_fee_vs_index'])}\n"
        f"- Shared-sink subset mean percentile: {_fmt(o['shared_sink']['mean_percentile'])} "
        f"(n={o['shared_sink']['count']}); independent: {_fmt(o['independent']['mean_percentile'])} "
        f"(n={o['independent']['count']})\n"
    )

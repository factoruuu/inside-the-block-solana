# Inside the Block — How Solana Validators Order Transactions

A reproducible measurement of the rule (if any) by which individual Solana
validators order transactions inside the blocks they produce: what makes one
transaction land earlier rather than later, how strictly, and whether the
apparent rule survives controlled experimentation.

**Method in one paragraph.** We target specific validators' 4-slot leader
windows on mainnet and fire bursts of our *own* transactions into them, with
experimentally controlled compute-unit price levels (randomly assigned, blind
to send order), interleaved send order, several independent actor keypairs,
and a deliberate subset sharing one writable account. Because every burst
transaction is ours, we know its intended variables exactly; the block itself
then reveals the ground-truth landing order. Our primary metric — the
relative order of our own transactions within a block — is immune to however
much foreign traffic shares the block. Full design: [DESIGN.md](DESIGN.md).

> Status: **measurement complete.** The live mainnet campaign ran on
> 2026-10-29 (post-Alpenglow; no pre-upgrade data is used). Full results,
> method, limitations, and the "what went wrong" log are in
> [REPORT.md](REPORT.md); the machine-readable outputs are in
> `data/analysis/`.

## Findings

**No detectable ordering rule — for any client class.** Across 51 bursts
and 612 self-sent transactions (612 landed, landing rate 1.000):

- **Fee concordance 0.497** (95% CI 0.463–0.532) — priority fee did not
  predict within-block landing order.
- **Send-order concordance 0.507** (95% CI 0.479–0.534) — arrival order
  did not either.
- **Spearman fee vs block index +0.006**; mean block percentile by CU
  price is non-monotone (0 fee → 0.484; 250k µ-lamports/CU → 0.503).
- **Lock probe:** shared-sink transactions averaged percentile 0.483 vs
  0.470 for independent ones — no lock-driven reordering detected.
- Per client class (fee concordance [CI]): agave-bam 0.472
  [0.410–0.534], jito 0.521 [0.450–0.588], harmonic-agave 0.479
  [0.404–0.555], harmonic-firedancer 0.446 [0.357–0.540], firedancer
  0.589 [0.442–0.736], firebam 0.551 [0.368–0.733] — every interval
  covers 0.5. Verdict per the pre-registered rule in DESIGN.md §7:
  **"no detectable rule"** everywhere. Total fees spent: 4,013,190
  lamports (0.004013 SOL) of the 0.05 SOL cap.

## Measurement log

| Date (WIB) | What | Slots | Notes |
|---|---|---|---|
| 2026-10-29 | Dry-run `plan` against mainnet RPC (read-only, nothing sent) | ~462,743,2xx–4xx | Selected 8 validators across 4 client classes; simulation path verified |
| 2026-10-29 11:28–12:18 | Live burst campaign (1 test burst + 50 campaign bursts, 612 txs) | 462,746,101–462,760,114 (epoch 1071) | Bursts aimed at 8 validators / 4 client classes; by actual leader the dataset covers 84 leaders / 7 client classes. Ledger total 4,013,190 lamports. See REPORT.md |

## Design summary

- **Bursts in leader windows.** The epoch leader schedule (note:
  `getLeaderSchedule` returns epoch-relative slot indices — handled in
  `leader.py`) gives each selected validator's upcoming 4-slot windows; the
  watcher polls `getSlot` and fires the burst into the window.
- **Controlled variables** (per burst of 12 txs): CU price from 5 levels
  (0 / 1k / 10k / 50k / 250k µ-lamports at a fixed 30,000 CU limit —
  measured consumption; the memo alone meters ~19k CU), assigned
  by a seeded shuffle that is *independent* of the send-order permutation;
  4 actor keypairs rotate as fee payers; 4 of 12 txs transfer to one shared
  sink account (write-lock probe), the rest to actor-unique sinks. Every tx
  is otherwise identical: compute-budget ixs + memo nonce + 1-lamport system
  transfer.
- **Metrics.** Per validator and per client class: pairwise concordance of
  fee order vs landing order, concordance of send order vs landing order
  (bootstrap 95% CIs), Spearman fee-vs-index, mean block-position percentile
  by fee level, shared-sink vs independent percentiles, and landing rates
  (including per fee level). A concordance whose CI covers 0.5 is reported
  as **"no detectable rule"** — that is a valid result, not a failure.
- **Client identification.** From `getClusterNodes`: the `clientId` field is
  primary (live mainnet finding: Agave, Jito and AgaveBam all report the
  same version strings, so version alone cannot separate them), version
  string is the fallback, validators.app cross-reference optional. The exact
  version + clientId + label of every selected validator is written to
  `data/analysis/validators.json`.

## The required considerations, and how the design handles them

- **Leader schedule & leader types** — §2/§3 of DESIGN.md. Windows are
  computed from the epoch schedule; slot→leader is also recorded for every
  block actually touched, and ordering analysis groups by the *actual*
  leader of each landing block, not the intended target.
- **Path of a transaction** — our backend → configured public RPC endpoint
  (`sendTransaction`, preflight on) → that node's forwarding toward the
  leader's TPU → the leader's banking stage. We use one endpoint for the
  whole campaign, never the Jito bundle API and never tips; Jito *validators*
  are measured as block producers like everyone else. Within-block relative
  order is invariant to whole-burst forwarding delay; residual per-tx
  forwarding jitter is why send-order concordance is *tested*, not assumed.
- **Our transactions interacting with each other** — multiple fee payers
  avoid self-serialisation; a unique memo per tx prevents signature
  collisions under one blockhash; baseline txs touch actor-unique accounts
  only, and lock contention exists solely in the deliberate probe subset.
- **Competition inside the block** — the primary metric compares our txs
  only to each other, so foreign traffic cannot move it; block size and our
  position percentile are recorded for absolute-position analyses.
- **Send order** — an independent random permutation, recorded per tx
  (`send_seq`, plus wall + monotonic timestamps), analysed as its own
  hypothesis (FIFO) against the fee hypothesis.
- **Noise vs rule** — pre-registered verdict language, bootstrap CIs,
  consistency across bursts, and effect sizes over p-values
  (DESIGN.md §7). The live campaign fired 50 bursts aimed across the 8
  selected validators; because bursts spill into neighbouring slots,
  per-validator statistics use the *actual* leader of each landing block
  (84 leaders observed), pooled per client class for the headline claims.

## What this design does NOT separate

- RPC forwarding behaviour vs the leader's own scheduler (single sending
  endpoint — the measured object is the composition of both).
- Client software defaults vs individual operator configuration within a
  client class.
- Bundle-derived ordering inside Jito validators' blocks (we never submit
  bundles; ordinary-TPU ordering is what we measure).
- CU price vs total priority fee (CU limit is fixed by design, so the two
  are collinear; senders control price-at-fixed-limit, which is what we
  measure).
- Congestion/time-of-day regimes other than those actually measured, and
  anything about pre-Alpenglow ordering.

## Safety: the spend cap

- Hard budget: **0.05 SOL total fees** (`SPEND_CAP_LAMPORTS`, default
  50,000,000 lamports). A persistent ledger (`data/spend-ledger.json`)
  counts only fees of transactions actually sent; every send is pre-checked
  against an exact fee estimate and the run hard-aborts rather than breach
  the cap. Planned/simulated transactions are never counted.
- Expected default-campaign cost at the design stage: ≈ 0.0102 SOL
  (~20% of the cap). **Actual campaign spend: 4,013,190 lamports
  (0.004013 SOL, 8.0% of the cap) for 612 sent transactions** — see
  `data/spend-ledger.json`.
- Keys live only in `KEYPAIR_DIR` (env/volume mount), are gitignored, and
  never appear in code, data, or this repo. The measurement wallet must be
  funded by the operator out-of-band; nothing here can move funds anywhere
  except 1-lamport transfers to deterministic sink addresses plus fees.

## Running it (one command per phase, Docker Compose)

```bash
cp .env.example .env   # set RPC_URL; CLUSTER only needed for live modes

docker compose run --rm itb plan        # DEFAULT dry-run: resolve validators,
                                        # show windows + a burst plan, simulate
                                        # one tx. Sends NOTHING.
docker compose run --rm itb init-keys   # generate actor keypairs into ./keys
                                        # (then fund them out-of-band)

# live (devnet rehearsal):
CLUSTER=devnet  RPC_URL=https://api.devnet.solana.com \
  docker compose run --rm itb run --live --max-bursts 20
# live (the real measurement — mainnet):
CLUSTER=mainnet-beta docker compose run --rm itb run --live

docker compose run --rm itb analyze     # offline: data/ -> stats + summary
```

Without Docker: Python 3.12, `pip install .`, then `itb plan|run|analyze`
with the same environment variables.

`run` refuses to send unless **both** `--live` is passed **and** `CLUSTER`
is set. Devnet note: the public RPC faucet (`requestAirdrop`) currently
returns HTTP 410 on both devnet and testnet public endpoints — fund devnet
actors via the web faucet if rehearsing there.

## Repository layout

```
REPORT.md            final measurement report (results, what went wrong)
DESIGN.md            full experiment design (read this first)
src/itb/
  config.py          env config, fee levels, live-send gate
  ledger.py          persistent spend ledger + hard cap
  rpc.py             raw JSON-RPC over httpx (no hidden retries/caching)
  validators.py      client classification (clientId-first) + selection
  leader.py          leader schedule (epoch-relative slots!) + window watch
  burst.py           seeded burst plans: fee assignment blind to send order
  txbuild.py         solders tx construction (CU budget + memo + transfer)
  sender.py          burst sending with per-tx records + cap enforcement
  collector.py       raw getBlock storage + position extraction
  analyze.py         concordance/Spearman/landing-rate stats -> CSV/JSON/MD
  cli.py             plan | run | analyze | init-keys | fund-devnet
tests/               pytest, no network (37 tests)
data/raw/            raw getBlock JSON, send-records.jsonl, landings.json
data/analysis/       validators.json, stats.json, joined-rows.csv, summary.md
```

**Stack choice.** Transaction building/signing uses **solders** (the
maintained Rust bindings — hand-rolling the wire format is a classic source
of silent measurement bugs), while RPC uses **raw httpx JSON-RPC**: we need
the verbatim `getBlock` JSON as evidence and exact `sendTransaction`
parameters, with no client library retrying or caching in between.
Statistics are implemented in-repo (`stats.py`, no scipy) so every number
in the report traces to code a judge can read.

## Verifying our data

Every landed transaction can be checked independently: pick a signature from
`data/raw/send-records.jsonl`, find its slot in `data/analysis/joined-rows.csv`,
call `getBlock` for that slot on any mainnet RPC (with
`maxSupportedTransactionVersion: 1` — required post-Alpenglow), and confirm
(a) the signature's index in the block matches `block_index`, and (b) the
block's leader (from the epoch leader schedule) matches `actual_leader`. The
raw `getBlock` responses we used are in `data/raw/block-<slot>.json`.

## What went wrong

The full, honest log is **REPORT.md §5**. The short version:

- **CU limit too low at first** — the memo meters ~19k CU against an
  initial 1,200 CU limit; fixed to a measured 30,000 CU for all txs.
- **Fresh-address sinks fail mainnet rent** — baseline redesigned to
  self-transfers plus one real, rent-exempt shared sink.
- **`getBlock` needed `maxSupportedTransactionVersion: 1`** post-Alpenglow
  — the collector crashed after the first successful burst; landings
  recovered from chain history.
- **Public-RPC 429s / dropped connections** — read-only calls retry with
  backoff; sends are *never* retried (a retry could double-spend the cap).
- **In-window collection missed many landings** (cached slot + slow
  collection) — fixed with per-validator slot refresh, `lead_slots`
  2 → 12, and a deterministic landing-recovery pass via
  `getSignaturesForAddress`. Final dataset: 612/612, zero unresolved.
- **Devnet rehearsal impossible** — RPC faucet returns HTTP 410; the
  first mainnet burst was run as a single-burst test instead.
- **Version strings no longer identify clients** (Agave/Jito/AgaveBam
  share "4.3.2") — classification uses `getClusterNodes` `clientId`;
  `getLeaderSchedule` is epoch-relative — offset handled in `leader.py`;
  solders has no memo helper — the memo ix is built by hand.

# Inside the Block — Measurement Report

**Question.** For each validator, by what rule does it order transactions
inside the blocks it produces — what decides whether one transaction lands
earlier rather than later, how strictly does that rule hold, and is there a
detectable rule at all?

**Verdict, up front.** With 612 of our own transactions landed across 51
bursts, we find **no detectable ordering rule** — neither by priority fee
nor by arrival (send) order — for any client class measured. Overall fee
concordance is 0.497 (95% CI 0.463–0.532), send-order concordance is 0.507
(95% CI 0.479–0.534), and the Spearman correlation between CU price and
within-block index is +0.006. Every per-client confidence interval covers
0.5. Under the decision language pre-registered in [DESIGN.md](DESIGN.md)
§7, the correct report for every validator and client class in this
dataset is **"no detectable rule at this effect size"** — landing position
of ordinary, non-bundle transactions arriving via the public RPC path
behaves as noise with respect to both fee level and send order, at the fee
levels and sample sizes measured. For the well-sampled client classes
the intervals bound any fee effect below a concordance of ≈ 0.59 (0.534
for agave-bam); the smaller classes are bounded more weakly. What this
rules out is a *strong* fee or FIFO rule, not an arbitrarily weak one.

---

## 1. When and where

| | |
|---|---|
| Date | **2026-10-29** (single day; sends 04:28:08–05:18:04 UTC = 11:28–12:18 WIB) |
| Cluster | Solana **mainnet-beta** |
| Era | **Post-Alpenglow only** (upgrade activated 2026-10-21; no pre-upgrade data mixed in) |
| Epoch | 1071 |
| Landed slot range | **462,746,101 – 462,760,114** |
| Bursts | 51 (1 single-burst mainnet test + 50 campaign bursts) |
| Transactions | 612 sent, **612 landed** (landing rate 1.000) |
| Fees spent | **4,013,190 lamports (0.004013 SOL)** of the 0.05 SOL hard cap (8.0%) |
| Raw evidence | 953 raw `getBlock` JSON files in `data/raw/`, plus `send-records.jsonl` and `landings.json` |
| Analysis outputs | `data/analysis/` (`stats.json`, `joined-rows.csv`, `summary.md`, `validators.json`, `leader-clients.json`) |

The spend ledger (`data/spend-ledger.json`, 612 entries — one per sent
transaction) is the authoritative fee record; every entry's signature can
be checked on-chain.

## 2. Method (summary — full design in DESIGN.md)

- **Self-transaction bursts in known leader windows.** We do not infer
  ordering from other people's transactions. For each targeted validator
  we fire bursts of 12 of our *own* transactions, timed from the epoch
  leader schedule into that validator's 4-slot leader window.
- **Controlled variables, everything else held constant.** Each burst tx
  is the same instruction shape (compute-budget limit + price, a unique
  memo nonce, a 1-lamport system transfer) at a fixed 30,000 CU limit.
  - **CU price** is drawn from 5 levels — 0 / 1k / 10k / 50k / 250k
    µ-lamports per CU — assigned by a seeded shuffle drawn *independently*
    of the send-order permutation, so fee and arrival order are
    decorrelated by construction.
  - **Send order** is a separate interleaved permutation, recorded per tx
    (`send_seq`, wall-clock + monotonic timestamps).
  - **4 actor keypairs** rotate as fee payers, so a single payer cannot
    serialise the burst against itself.
  - **Lock probe:** 4 of 12 txs in each burst transfer to one common,
    real, rent-exempt sink account, so they all write-lock the same
    account; the other 8 use actor-unique accounts.
- **Metrics (pre-registered).** Primary: pairwise concordance, within the
  same block, between (a) fee order and landing order and (b) send order
  and landing order — a metric foreign traffic cannot move, because it
  only compares our txs to each other. Secondary: within-block position
  percentile (index / (block tx count − 1)), Spearman fee-vs-index, mean
  percentile by fee level, shared-sink vs independent percentiles, and
  landing rates (overall and per fee level). Statistics are reported as
  effect sizes with bootstrap 95% CIs, never bare p-values.
- **Attribution by actual leader.** A burst aimed at one validator's
  window does not all land under that validator: slot times are ~400 ms,
  forwarding latency is of the same order, and bursts were deliberately
  sent across the window. Every landed tx is therefore labelled with the
  *actual* leader of its block (from the leader schedule), and all
  per-validator/per-client ordering statistics group by actual leader.
  This is what makes the dataset verifiable rather than aspirational.
- **Path.** All sends went through one public RPC endpoint
  (`api.mainnet-beta.solana.com`, `sendTransaction`, preflight on), never
  the Jito bundle API, never tips. See §6 for what that does and does not
  let us claim.
- **Budget safety.** A persistent ledger counts only fees of transactions
  actually sent, estimates each fee before sending, and hard-aborts rather
  than breach `SPEND_CAP_LAMPORTS` (50,000,000). Actual spend was
  4,013,190 lamports.

## 3. Coverage

### 3.1 Targeted validators (the aim points)

Bursts were aimed at the windows of these 8 validators, selected
deterministically (2 highest-stake per client class, classes by descending
total stake) spanning 4 client classes. Client identity comes from the
`clientId` field of `getClusterNodes` — see §5(g) for why version strings
cannot be used.

| Node pubkey | Client class (clientId) | Version | Bursts aimed | Txs sent | Txs landed | …of which under the target itself |
|---|---|---|---:|---:|---:|---:|
| `CAo1dCGYrB6NhHh5xb1cGjUiu86iyCfMTENxgHumSve4` | harmonic-agave (HarmonicAgave) | 4.3.2 | 6 | 72 | 72 | 20 |
| `Fd7btgySsrjuo25CJCj7oE7VPMyezDhnx7pZkj2v69Nk` | harmonic-agave (HarmonicAgave) | 4.3.2 | 7 | 84 | 84 | 6 |
| `HEL1USMZKAL2odpNBj2oCjffnFGaYwmbGmyewGv1e2TU` | jito (JitoLabs) | 4.3.2 | 7 | 84 | 84 | 15 |
| `E1r4Psq84tHfQ6aPTvvDka4U3u8zPVD7gEUrH25RdxHL` | jito (JitoLabs) | 4.3.2 | 6 | 72 | 72 | 16 |
| `DRpbCBMxVnDK7maPM5tGv6MvB3v1sRMC86PZ8okm21hy` | agave-bam (AgaveBam) | 4.4.0-rc.1 | 6 | 72 | 72 | 12 |
| `5Cchr1XGEg7dbBXByV5NY2ad8jfxAM7HA3x8D56rq9Ux` | agave-bam (AgaveBam) | 4.3.2 | 6 | 72 | 72 | 11 |
| `JUPiTERrZqgf1jUyR7dSkhMx4Kn2qJyekWsg3LT1h4b` | harmonic-firedancer (HarmonicFiredancer) | 26.10.4 | 6 | 72 | 72 | 14 |
| `Awes4Tr6TX8JDzEhCZY2QVNimT6iD1zWHzf1vNyGvpLM` | harmonic-firedancer (HarmonicFiredancer) | 26.10.4 | 6 | 72 | 72 | 11 |

(Vote pubkeys and activated stake for each are in
`data/analysis/validators.json`. The one additional burst — the initial
single-burst mainnet test, §5(f) — carried no target.)

Only 105 of 600 campaign transactions landed in a block led by the
validator they were aimed at; the rest landed in neighbouring slots under
other leaders. That spread is expected given ~400 ms slots and
public-RPC forwarding latency, and it is precisely why all ordering
statistics are computed against **actual** leaders. No transaction is
counted toward a validator that did not produce its block.

### 3.2 Dataset-wide coverage (by actual leader)

Because of that spillover, the landed dataset covers **84 distinct
leaders** across **7 client classes** — broader than the 8 aim points:

| Client class | Same-block landed txs | Share |
|---|---:|---:|
| agave-bam | 172 | 28.1% |
| jito | 157 | 25.7% |
| harmonic-agave | 123 | 20.1% |
| harmonic-firedancer | 88 | 14.4% |
| firedancer | 38 | 6.2% |
| firebam | 27 | 4.4% |
| agave | 7 | 1.1% |
| **Total** | **612** | 100% |

The brief's minimum — ≥ 6 validators spanning ≥ 3 client/forks — is met
both by the targeted selection (8 validators, 4 classes) and, with margin,
by the actual-leader dataset (84 leaders, 7 classes). The plain-`agave`
class is represented by only 7 transactions from spillover and is reported
for completeness; no conclusion rests on it.

## 4. Results

### 4.1 Overall

| Statistic | Value |
|---|---|
| Sent / landed | 612 / 612 (rate 1.000) |
| Fee concordance | **0.497** (95% CI 0.463–0.532) |
| Send-order concordance | **0.507** (95% CI 0.479–0.534) |
| Spearman, CU price vs within-block index | **+0.006** |
| Shared-sink subset mean percentile | 0.483 (n = 204) |
| Independent subset mean percentile | 0.470 (n = 408) |

A concordance of 0.5 is chance. Both candidate rules sit on top of it,
with confidence intervals that include it and exclude any strong effect:
at this sample size (612 same-block txs, ~148k untied fee pairs), a fee
rule with concordance ≥ ~0.56 overall would have cleared the CI bound. It
did not come close.

### 4.2 Per client class

| Client class | n | Fee concordance [95% CI] | Send-order concordance | Spearman fee vs index | Verdict |
|---|---:|---|---|---|---|
| agave-bam | 172 | 0.472 [0.410–0.534] | 0.539 | +0.070 | No detectable rule |
| jito | 157 | 0.521 [0.450–0.588] | 0.513 | −0.046 | No detectable rule |
| harmonic-agave | 123 | 0.479 [0.404–0.555] | 0.469 | +0.051 | No detectable rule |
| harmonic-firedancer | 88 | 0.446 [0.357–0.540] | 0.508 | +0.128 | No detectable rule |
| firedancer | 38 | 0.589 [0.442–0.736] | 0.494 | −0.224 | No detectable rule (wide CI, small n) |
| firebam | 27 | 0.551 [0.368–0.733] | 0.556 | −0.115 | No detectable rule (wide CI, small n) |
| agave | 7 | 0.500 [0.000–1.000] | 0.600 | 0.000 | Uninformative (n = 7, spillover only) |

No client class shows a fee rule; none shows an arrival (FIFO) rule
either. The classes with the tightest intervals (agave-bam, jito,
harmonic-agave — the ones producing most of the measured blocks) bound
any fee effect to a concordance below ≈ 0.59, and their point estimates
straddle 0.5 in both directions (0.472 / 0.521 / 0.479), which is the
signature of noise, not of a weak-but-consistent rule. Per-validator
detail for all 84 leaders is in `data/analysis/summary.md` and
`stats.json`; individual validators with small n swing wildly (as
expected under the null) and none is singled out, per the
multiple-comparison policy in DESIGN.md §7.

### 4.3 Mean block-position percentile by fee level

If priority fee bought earlier placement, mean percentile would fall
monotonically as CU price rises (0 = top of block). It does not:

| CU price (µ-lamports/CU) | n | Mean position percentile | Landed / sent |
|---:|---:|---:|---:|
| 0 | 153 | 0.484 | 153 / 153 |
| 1,000 | 153 | 0.485 | 153 / 153 |
| 10,000 | 102 | 0.424 | 102 / 102 |
| 50,000 | 102 | 0.468 | 102 / 102 |
| 250,000 | 102 | 0.503 | 102 / 102 |

The highest fee level measured lands, on average, at the *middle* of the
block (0.503) — indistinguishable from the zero-fee level (0.484) — and
the sequence is non-monotone. Fee level also did not change landing
probability: every level landed 100% of its transactions.

### 4.4 Lock probe (shared writable account)

One third of each burst (204 txs) write-locked a single shared sink
account; the rest (408 txs) touched actor-unique accounts. If lock
contention serialised, delayed, or batched the probe transactions, their
mean block percentile would differ systematically from the independent
subset. It does not: **0.483 (shared) vs 0.470 (independent)** — a
1.3-percentile-point gap, well inside noise at these sample sizes, and
inconsistent in sign across client classes (e.g. firebam 0.636 vs
firedancer 0.347 on small n). We detect no lock-driven reordering effect
at this scale.

### 4.5 Landing rate

612 sent, 612 landed — a landing rate of **1.000**, overall and at every
fee level (§4.3). Two qualifications, stated plainly:

1. This is the *eventual* landing rate within the observation and
   recovery horizon, not the in-window rate. In-window collection missed
   many landings in real time (§5(e)); all of them were subsequently
   recovered deterministically from chain history, and zero signatures
   remained unresolved.
2. A 100% eventual landing rate at every fee level — including zero
   priority fee — is itself a finding about the measured regime: during
   this window, blocks were not full enough for fee-based *inclusion*
   competition to bind on transactions of this shape, which is consistent
   with fee-based *ordering* not binding either. We do not extrapolate
   this to congested regimes (§6).

### 4.6 The verdict, with its statistical support

Applying the pre-registered decision rule (DESIGN.md §7) — "fee rule"
requires fee concordance clearly above both 0.5 and send-order
concordance; "arrival rule" the reverse; CIs covering 0.5 mean "no
detectable rule":

- **Overall:** fee 0.497 [0.463–0.532], send-order 0.507 [0.479–0.534],
  Spearman +0.006 → **no detectable rule**.
- **Every client class:** fee CI covers 0.5 → **no detectable rule**,
  for agave-bam, jito, harmonic-agave, harmonic-firedancer, firedancer,
  and firebam alike (agave uninformative at n = 7).
- **Lock probe:** no detectable lock effect.
- **Inclusion:** fee did not affect landing probability at any level.

In plain terms: for ordinary transactions submitted through the public
RPC path, with priority fees up to 250k µ-lamports/CU, *neither paying
more nor arriving earlier measurably changed where a transaction landed
inside the blocks these validators produced on 2026-10-29.* The ordering
we observe is consistent with the burst's transactions being interleaved
into the block at positions unrelated to the two candidate rules we
could control — i.e. dominated by factors upstream of, or orthogonal to,
fee and arrival order (see §6).

## 5. What went wrong

An honest log of the failures, in the order they bit. Several changed the
design or the code; none changed the result after repair, and the final
dataset (612/612 landed, chain-verified) postdates all of them.

**(a) CU limit initially too low.** The burst transaction was first built
with a 1,200 CU limit. Simulation showed the memo instruction alone
meters ~19,083 CU, so every transaction would have failed at execution.
Fixed by measuring actual consumption and setting the fixed limit to
30,000 CU for all transactions (`config.py`), which also re-based the
priority-fee arithmetic (price × 30,000 CU; max priority fee per tx
7,500 lamports at the 250k level).

**(b) Fresh-address sinks fail rent.** The original baseline sent
1-lamport transfers to fresh derived sink addresses; on mainnet those
fail the rent-exempt rule (a 0-byte account must hold ≥ 890,880 lamports
to persist). The baseline was redesigned: independent transactions are
self-transfers (actor → itself, no new account), and the lock probe uses
**one real, separately funded, rent-exempt sink account** (funded with
1,000,000 lamports) shared by all probe transactions.

**(c) getBlock broke on post-Alpenglow transaction versions.** After the
first successful live burst, the collector crashed: post-Alpenglow blocks
contain transaction version 1, and the `getBlock` request needed
`maxSupportedTransactionVersion: 1`. The burst itself had landed fine;
its block data was recovered after the collector fix. No sends were
repeated because of this.

**(d) Public-RPC rate limits and transport drops.** The public endpoint
returned HTTP 429s and dropped connections throughout the campaign. Policy
that kept this from corrupting the measurement: **read-only calls
(`getBlock`, `getSignaturesForAddress`, `getSlot`) retry with backoff;
sends are never retried** — a retried send can double-spend the fee
budget and duplicate a burst slot. The ledger only counts signatures the
RPC actually returned.

**(e) Run loop missed in-window collection for many bursts (the big
one).** The campaign loop cached the current slot and collected blocks
too slowly, so for many bursts the in-window collection came back empty
even though the transactions had landed. Combined with §5(c), early
snapshots showed as few as 55 of 300 landings. Fixes: refresh the slot
per validator instead of using a cached value; raise `lead_slots` from 2
to 12 so bursts are armed earlier; and, decisively, add a **deterministic
landing-recovery pass** — for every actor, pull `getSignaturesForAddress`
history, match it against the send records, and fetch the exact landing
blocks (this is `landings.json`). Recovery rounds closed the dataset in
stages (300/300, then 600/600, then **612/612 with zero unresolved
signatures**). The lesson is recorded for reproducers: never trust
in-window collection as the landing record; the chain itself is the
record, and it is queryable after the fact.

**(f) Devnet rehearsal was impossible.** The devnet/testnet public RPC
faucet (`requestAirdrop`) returns HTTP 410 on both, so the planned free
devnet end-to-end rehearsal could not be funded. Instead, the first
mainnet burst was run as a deliberate **single-burst test** (12 txs,
~0.00008 SOL) and fully verified — fees, landings, positions — before the
50-burst campaign was allowed to proceed.

**(g) Version strings no longer identify clients.** Stock Agave, Jito and
AgaveBam nodes all report version "4.3.2" (and Firedancer reports both
26.10.x and 0.1.1), so the brief's "identifiable by version string" route
would have silently merged distinct clients. Classification therefore
uses the `clientId` field of `getClusterNodes` as the primary signal,
with version recorded alongside for audit. This also produced the class
labels used throughout this report (e.g. `harmonic-agave`,
`agave-bam`, `firebam` are distinct clientIds, reported as returned).

**Smaller notes.** solders (current versions) has no memo helper — the
memo instruction is built by hand in `txbuild.py`. `getLeaderSchedule`
returns epoch-relative slot indices (0–431,999); the first dry-run found
zero windows until the epoch offset was applied (`leader.py`, covered by
a unit test). This VM's egress proxy breaks stock httpx defaults;
`rpc.py` handles proxy/CA environment explicitly — harmless elsewhere.

## 6. Limitations — what this does not show

- **Single RPC send path.** All transactions arrived via one public RPC
  endpoint and its forwarding toward each leader's TPU. Results describe
  ordering *as seen through the public RPC path*, including that path's
  forwarding behaviour. Per-transaction forwarding jitter cannot be
  separated from the leader's own reordering with a single endpoint —
  indeed, the collapse of *both* concordances to 0.5 is consistent with
  arrival order being scrambled upstream of the leader. A direct-TPU /
  staked-connection design could separate the two; we do not claim to.
- **One day, one epoch, one congestion regime.** All data is from
  2026-10-29, epoch 1071, in a regime where every transaction landed and
  blocks were not fee-competitive for inclusion. Under congestion, fee
  ordering may bind; nothing here speaks to that regime.
- **Simple transactions only.** Transfer + memo at a fixed 30,000 CU
  limit. Compute-heavy, multi-account, or contention-heavy transactions
  may be scheduled differently.
- **Fee range bounded.** Priority fees were tested up to 250k
  µ-lamports/CU (7,500 lamports/tx at the fixed limit). We make no claim
  about extreme fee levels.
- **Ordering among our own transactions + block percentile.** The
  primary metric is the relative order of *our* transactions and their
  percentile in the block — not a claim about the ordering rule for all
  traffic in the block, most of which arrives by paths we cannot observe.
- **Client class ≠ proven cause.** Classes are assigned from
  self-reported `clientId`; validators in a class may be configured
  differently by their operators. We report class-level aggregates, not
  software-caused effects.
- **Jito bundles/tips out of scope by design.** For jito-class leaders we
  measured ordinary TPU transactions in their blocks. Bundle-derived
  ordering inside the same blocks is context, not separately identified;
  we never submitted a bundle or a tip.

## 7. Reproducibility and verification

**Verify any claim from the committed data.** Pick any signature from
`data/raw/send-records.jsonl` (or any row of
`data/analysis/joined-rows.csv`), note its `landed_slot`, and call
`getBlock` for that slot on any mainnet RPC with
`maxSupportedTransactionVersion: 1`. Check that (a) the signature appears
at the recorded `block_index`, and (b) the epoch leader schedule names
`actual_leader` as that slot's leader. The raw `getBlock` responses we
used are committed as `data/raw/block-<slot>.json` (953 files), so
verification does not even require trusting our RPC — only the chain.

**Re-run the analysis offline.** The analyzer consumes only committed
data (`data/raw/send-records.jsonl`, `data/raw/landings.json`, the raw
blocks, `data/analysis/validators.json` + `leader-clients.json`):

```bash
docker compose run --rm itb analyze
# or, without Docker:
pip install . && itb analyze
```

This regenerates `data/analysis/stats.json`, `joined-rows.csv`, and
`summary.md`; every number in §3–§4 of this report comes from those
files.

**Re-run the measurement.** Dry-run first (sends nothing):

```bash
docker compose run --rm itb plan
```

Live sending requires both `--live` and the `CLUSTER` env var, actor
keypairs in `KEYPAIR_DIR` (never in the repo), and is bounded by the
0.05 SOL spend cap described in §2. Full instructions: README.md.
Note that a re-run measures a *new* window of network time — it tests
whether our null result replicates, which is the strongest check on it
we know how to offer.

**Test suite.** `pytest` (37 tests, no network) covers the spend-cap
ledger, burst-plan seeding/decorrelation, position extraction from canned
`getBlock` payloads, leader-schedule epoch offsets, client
classification, and the concordance/Spearman statistics against known
values.

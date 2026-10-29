# Inside the Block — Experiment Design

**Question.** For each validator, by what rule does it order transactions inside the
blocks it produces? Concretely: what decides whether one transaction lands earlier
rather than later in the same block, how strictly is that rule followed, and is
there a detectable rule at all — or is landing position effectively noise once
basic mechanics are accounted for?

**Scope.** Solana mainnet-beta only. All measurements are post-Alpenglow
(the Alpenglow consensus upgrade activated 2026-10-21); no pre-upgrade data is
mixed in. Measurement window: see README "Measurement log" for exact dates/slots
of each live run.

---

## 1. Core method: self-transaction bursts inside known leader windows

We do not try to infer ordering rules from other people's transactions — their
send times, fee intent, and routing are unobservable, so any "rule" fitted to
them confounds the sender's behaviour with the leader's. Instead, the primary
evidence is **transactions we send ourselves**, with experimentally controlled
variables, sent so that they land in the blocks of a *known, targeted leader*
during that leader's 4-slot window.

For each targeted validator we run repeated **bursts**:

- A burst is a small batch (default 12) of our own transactions, constructed to
  be as identical as possible except for the variables under test, and fired in
  rapid sequence shortly before / during the target leader's window so that as
  many as possible land in the same block (ideally) or the same 4-slot window.
- Because all burst transactions are ours, we know each one's exact fee level,
  send timestamp (local, monotonic + wall clock), send order, actor, and
  intended variable assignment. The block then tells us the ground truth: the
  index at which each of our signatures actually executed.
- **Primary metric: relative landing order of our own transactions within the
  block.** For every pair of our transactions that landed in the same block we
  ask whether their landing order agrees with the hypothesised rule (e.g.
  higher fee first). Pairwise concordance is *robust to external competition*:
  other users' transactions interleaved between ours do not change the relative
  order of our transactions among themselves, so the metric survives arbitrary
  block fullness.
- **Secondary metric: normalised block position percentile** — index /
  (block tx count − 1) per transaction — used for cross-block and cross-validator
  comparisons where absolute indices are meaningless because blocks differ in
  size.

### 1.1 Variables under test

1. **Compute-unit price (priority fee).** Each burst transaction is assigned one
   of several discrete CU-price levels (default: 0, 1k, 10k, 50k, 250k
   micro-lamports/CU at a fixed CU limit, so total fee ordering ≡ price
   ordering). Assignment is **randomised per burst from a recorded seed and
   blind to send order** — the sender process fires in send-order sequence
   without "knowing" which fee it is sending next in any systematic pattern;
   the assignment permutation and the send-order permutation are drawn
   independently. This breaks the fee↔arrival-time confound that ruins naive
   fee-vs-position correlations.
2. **Send order / arrival order.** Within a burst, send sequence is an
   interleaved permutation (not sorted by fee, not grouped by actor). If a
   leader orders purely by arrival (FIFO through its banking stage), send order
   should predict landing order as well as or better than fee does.
3. **Actor identity.** A burst is spread across **multiple independent actor
   keypairs** (default 4). A single fee payer serialises itself: transactions
   from one account must execute in nonce/blockhash order and, more importantly,
   a single writable fee-payer account makes all of them contend on the same
   account lock, which can impose an artificial order that has nothing to do
   with the leader's policy. Multiple actors remove self-serialisation from the
   baseline measurement.
4. **Shared writable account (lock probe).** A deliberate subset of each burst
   (default 4 of 12) transfers to one *common* sink account, so those
   transactions all write-lock the same account and cannot execute in parallel
   across banking threads. Comparing the subset's internal landing order against
   its send order and fee assignment tests whether lock contention reorders,
   delays, or batches those transactions relative to the independent ones.

Everything else is held constant within a burst: same instruction shape
(compute-budget limit + price, memo nonce, 1-lamport system transfer), same CU
limit, same recent blockhash where possible, same sending endpoint, same host.

### 1.2 Hypotheses and statistics

Per validator (and pooled per client class), on same-block pairs of our txs:

- **H_fee:** higher CU price ⇒ earlier landing. Measured by (a) pairwise
  concordance of (fee order, landing order), (b) Spearman correlation between
  CU price and within-block rank of our txs, (c) mean position percentile by
  fee level.
- **H_fifo:** earlier send ⇒ earlier landing. Same statistics with send
  sequence in place of fee. Comparing H_fee vs H_fifo concordance tells us
  which rule — if either — the leader's scheduler actually expresses.
- **H_lock:** transactions sharing a writable account land in send order more
  strictly (serialisation) and/or at systematically worse percentiles than
  independent transactions at the same fee level.
- **Null result is a valid conclusion.** If, with adequate repetitions, neither
  fee nor send order predicts landing order above chance (concordance ≈ 0.5,
  confidence interval covering 0.5), the correct report for that validator is
  "no detectable rule at this effect size", not a forced story. We report
  effect sizes with bootstrap confidence intervals, never bare p-values.

Repetitions: default plan is ≥ 20 bursts per validator across ≥ 6 validators
(see §3), giving hundreds of same-block pairs per validator — enough to detect
a concordance of ≈ 0.60 vs the 0.50 null at conventional power, and to bound
smaller effects honestly if absent.

### 1.3 Landing rate is data, not waste

Not every sent transaction lands in the target window (or at all). We record
every sent signature and classify its outcome: landed in target block / landed
in the same leader window but different slot / landed under a *different*
leader / never landed within the observation horizon. Landing rate per
validator, per fee level, and per actor is reported. A fee level that changes
*landing probability* but not *within-block order* is itself a finding about
how the leader treats transactions, and dropping non-landed transactions
silently would bias the ordering statistics (survivorship), so they stay in
the dataset and in the report.

---

## 2. The path of a transaction, and what we do about each hop

`our backend → RPC endpoint → (TPU forwarding / gossip) → leader's TPU →
banking stage threads → block`. The brief requires us to state what sits
between our backend and the executing node and how the design handles it:

- **RPC endpoint.** We submit via `sendTransaction` to a single configured
  RPC endpoint (env `RPC_URL` / optional separate `SEND_RPC_URL`) and never
  switch endpoints mid-experiment. A public RPC node is *not* the leader: it
  forwards the transaction toward the current/next leader's TPU. Forwarding
  adds variable latency and the RPC's own view of the leader schedule can lag.
  Mitigations: bursts are timed off the *chain's* leader schedule (read from
  our RPC) with a lead time, and we analyse **relative order within a block**,
  which is invariant to a constant-ish forwarding delay applied to the whole
  burst. Residual risk (per-transaction forwarding jitter scrambling arrival
  order at the leader) is precisely why H_fifo is tested rather than assumed —
  if arrival order is destroyed upstream of the leader, send-order concordance
  collapses toward 0.5 for *every* validator, which is itself informative and
  is reported as a path effect, not a validator effect.
- **What we do not do:** no Jito bundle API, no tips — Jito *validators* are in
  scope as block producers, but the bundle mechanism is explicitly not the
  mechanism under study. No private relay / staked-connection fast lane: the
  ordinary public path is the measurement object. (If the ordinary path goes
  through a Jito-enabled RPC's forwarding, that is part of the measured path
  and is disclosed in the run log.)
- **Leader types.** The leader schedule contains a mix of client
  implementations (stock Agave, Jito's Agave fork, Frankendancer, full
  Firedancer). Client identity is assigned from `getClusterNodes` version
  strings, cross-referenced with validators.app where available, and recorded
  per validator in the output. Client classification is heuristic — version
  strings are self-reported — and the report says so. Slot-level leader
  identity for every landed block is taken from the leader schedule and stored
  with the raw data, so a misclassified or re-scheduled slot is detectable in
  verification.

## 3. Validator selection

- Pull `getVoteAccounts` (current) + `getClusterNodes`; join on vote pubkey /
  node pubkey; classify client primarily from the `clientId` field of
  `getClusterNodes` (resolved to a name by current RPCs: Agave, JitoLabs,
  AgaveBam, Firedancer, Frankendancer, Harmonic*, FireBAM, …), falling back
  to version-string heuristics on older RPCs. **Live finding (2026-10-29):
  version strings alone no longer identify the client** — stock Agave, Jito
  and AgaveBam nodes all report identical versions (e.g. 4.3.2), and
  Firedancer reports both 26.10.x and 0.1.1. Any design keyed on version
  strings alone would silently merge distinct clients; we record version,
  clientId, and our class label for every selected validator so the mapping
  is auditable.
- Require **≥ 6 validators spanning ≥ 3 client classes**. Selection takes
  client classes in descending total-stake order (the clients that produce
  most blocks), 2 highest-stake validators per class, until ≥ 8 validators
  across ≥ 3 classes. Prefer high-stake validators (they lead often, making
  window targeting practical) but record stake so any stake effect is
  visible. A live `plan` run on 2026-10-29 selected 8 validators across
  harmonic-agave, jito, agave-bam and harmonic-firedancer.
- The final selection, with pubkeys, version strings, client labels, and stake,
  is written to `data/analysis/validators.json` at run time and quoted in the
  report. Selection is deterministic (sorted by stake within class) given the
  cluster state at selection time.

## 4. Leader-window targeting

- Fetch the epoch leader schedule (`getLeaderSchedule` for the relevant slot),
  invert it to slot → leader, and find upcoming windows for selected
  validators. A window is 4 consecutive slots.
- Timing: refresh the recent blockhash shortly before the window; arm the
  burst at (window start − lead), with lead configurable (default ≈ 2 slots
  before window start, sending through the window). Slot times post-Alpenglow
  are ~400 ms, so the watcher polls `getSlot` and sleeps in short increments
  rather than trusting wall-clock estimates; every send records both the
  local timestamp and the chain slot observed immediately before the burst.
- Missed windows happen (skipped slots, late blockhash, RPC lag). A burst
  whose transactions land outside the target window is still recorded and
  labelled with the *actual* leader of each landing slot; analysis of
  per-validator ordering uses actual, not intended, leader identity. That
  labelling is what makes the dataset verifiable rather than aspirational.

## 5. Competition inside the block

Our burst is never alone in the block. Design responses:

- Primary metric (pairwise relative order of *our* txs) is unaffected by how
  many foreign transactions sit between ours.
- Position percentile normalises for block size when absolute position is used.
- We record block metadata (total tx count, block time, leader) for every
  block we touch, so congestion at measurement time is visible and can be
  included as a covariate / sanity check (e.g. does fee concordance rise in
  full blocks, where ordering is actually contested?).
- Bursts are small (12 txs) against typical block sizes in the thousands, so
  our own traffic does not materially change the competition we are measuring.

## 6. Interaction of our own transactions with each other

- **Fee-payer serialisation:** avoided in the baseline by using 4 actors
  (see §1.1.3); each actor's transactions in a burst share a blockhash but
  differ by memo nonce, so signatures are unique.
- **Account locks:** baseline transactions touch only actor-unique accounts
  (actor as payer/writable + its own sink). Only the deliberate probe subset
  shares a writable sink (§1.1.4), so lock effects are measured, not suffered
  silently.
- **Blockhash expiry:** one blockhash per burst; if sends straddle its
  validity (~150 slots) the later sends are rebuilt or the burst is marked
  degraded in the log. Bursts are seconds long, so this should not trigger;
  the handling exists so it is visible if it does.
- **Duplicates:** identical actor+instruction+blockhash would collide
  signatures; a unique memo per transaction prevents this by construction.

## 7. Noise vs rule — how we decide

- Pre-registered decision language: for each validator we report (i) fee
  concordance with bootstrap 95% CI, (ii) send-order concordance with CI,
  (iii) the difference between them. "Fee rule" ≈ fee concordance clearly
  above both 0.5 and send-order concordance; "arrival rule" ≈ the reverse;
  "mixed" if both are elevated; **"no detectable rule"** if CIs cover 0.5.
- The same analysis pooled by client class tests whether "rules" are actually
  client-software defaults rather than operator choices.
- Multiple-comparison honesty: with ≥ 6 validators × several statistics, some
  nominal "effects" will appear by chance; the report emphasises effect sizes
  and consistency across bursts (e.g. sign of per-burst concordance) over
  isolated significance.

## 8. Budget and safety (hard constraints from the brief)

- Entire measurement ≤ ~0.05 SOL in fees. `SPEND_CAP_LAMPORTS` defaults to
  50,000,000 (0.05 SOL) and the code enforces it: a persistent ledger counts
  only fees of transactions **actually sent** (signature returned by RPC),
  estimates each transaction's fee *before* sending (base fee + CU-limit ×
  CU-price), and hard-aborts the run when the next transaction would breach
  the cap. Simulated / planned transactions cost nothing and are never counted.
- Expected consumption of the default plan: per-tx fee ≈ 5,000 lamports base
  + ≤ 300 lamports priority at the default levels ≈ ≤ 5,300; 12 txs/burst ×
  20 bursts × 8 validators ≈ 1,920 txs ≈ ≤ 0.0102 SOL — about 20% of the cap,
  leaving headroom for retries and extra validators.
- **As-run note (2026-10-29):** the CU limit was raised to 30,000 after
  measuring actual memo consumption (REPORT.md §5a), raising the maximum
  priority fee to 7,500 lamports/tx; the executed campaign sent 612
  transactions in 51 bursts for **4,013,190 lamports total (8.0% of the
  cap)**. The cap logic itself was unchanged and never approached.
- Dry-run by default: `plan` mode sends nothing. Live sending requires both
  the `--live` flag and the `CLUSTER` env var; keys are loaded from
  `KEYPAIR_DIR` (env/volume) and are never written into the repo or the data
  outputs.

## 9. Reproducibility and verifiability

- One command via Docker Compose for each phase (`plan`, `run`, `analyze`).
- All raw data is published: every sent signature, its assignment record
  (fee level, actor, send order, timestamps, target/actual slot), the raw
  `getBlock` JSON for every touched slot (`data/raw/`), and the leader
  schedule slice used. A judge can pick any signature, call `getBlock` for
  its slot, and confirm its index and the block's leader independently.
- Randomness is seeded and recorded (burst plan JSON includes the seed), so
  the assignment permutations are exactly reconstructible.
- Analysis consumes only the published raw data + send records; re-running
  `analyze` must reproduce the report tables byte-for-byte (modulo timestamps
  in headers).

## 10. What this design does NOT separate (explicit limitations)

- **RPC forwarding vs leader policy.** We observe the composition of
  (our path to the leader) + (leader's scheduler). Per-transaction jitter in
  forwarding cannot be separated from the leader's own reordering with a
  single sending endpoint. A multi-endpoint or direct-TPU design could
  separate these; it is out of scope and we do not claim otherwise.
- **Client software vs operator configuration.** Validators running the same
  client can configure it differently; with ~2 validators per class we can
  note consistency, not prove the software is the cause.
- **Jito-internal ordering.** For Jito validators we measure the ordering of
  ordinary TPU transactions in their blocks. Bundle-derived ordering inside
  the same blocks is part of the block's context but is not separately
  identified; we never submit bundles.
- **Fee level vs absolute fee.** CU limit is fixed, so price and total
  priority fee are perfectly collinear by design. We measure response to the
  fee signal a normal sender controls (CU price at fixed limit), not which
  of the two formulations the scheduler "uses".
- **Time-of-day / congestion regimes.** Runs occur at specific times; results
  are stated for the measured congestion regime, not extrapolated to all
  market conditions.
- **Post-Alpenglow only.** Nothing here describes pre-Alpenglow ordering, and
  skipped-slot behaviour under Alpenglow is recorded where observed, not
  modelled.

## 11. Failure modes — expected vs actual

Expected at design time: missed/skipped windows, bursts landing under the
wrong leader, blockhash expiry, RPC rate limits, faucet / funding friction
on test clusters, client-class imbalance in the live leader schedule.
All of these occurred in some form — plus several we did not expect (CU
metering of the memo, rent-exempt sink failures, post-Alpenglow `getBlock`
version requirements, version strings ceasing to identify clients). The
authoritative account of what *actually* went wrong, and how each failure
was repaired, is **REPORT.md §5**.

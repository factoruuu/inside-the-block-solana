import random
from collections import Counter

from itb.burst import assign_fee_levels, plan_burst

LEVELS = [0, 1_000, 10_000, 50_000, 250_000]


def test_assignment_is_balanced():
    fees = assign_fee_levels(10, LEVELS, random.Random(42))
    counts = Counter(fees)
    assert set(counts) == set(LEVELS)
    assert all(c == 2 for c in counts.values())  # 10 txs / 5 levels


def test_assignment_deterministic_per_seed():
    a = plan_burst(seed=7, burst_size=12, fee_levels=LEVELS)
    b = plan_burst(seed=7, burst_size=12, fee_levels=LEVELS)
    assert [t.cu_price_micro for t in a.txs] == [t.cu_price_micro for t in b.txs]
    assert [t.send_seq for t in a.txs] == [t.send_seq for t in b.txs]


def test_assignment_varies_with_seed():
    plans = {tuple(t.cu_price_micro for t in plan_burst(seed=s, fee_levels=LEVELS).txs) for s in range(20)}
    assert len(plans) > 15  # assignments actually shuffle


def test_send_order_is_a_permutation_and_decorrelated_from_fee():
    # Across many seeds, the correlation between a tx's fee rank and its send
    # position must be weak — send order must not leak fee information.
    from itb.stats import spearman

    corrs = []
    for seed in range(50):
        plan = plan_burst(seed=seed, burst_size=12, fee_levels=LEVELS)
        in_order = plan.in_send_order()
        assert sorted(t.tx_index for t in in_order) == list(range(12))
        fees_in_send_order = [t.cu_price_micro for t in in_order]
        seq = list(range(12))
        c = spearman([float(f) for f in fees_in_send_order], [float(s) for s in seq])
        if c is not None:
            corrs.append(abs(c))
    assert corrs and (sum(corrs) / len(corrs)) < 0.45


def test_shared_subset_and_actor_rotation():
    plan = plan_burst(seed=3, burst_size=12, num_actors=4, shared_subset_size=4, fee_levels=LEVELS)
    assert sum(1 for t in plan.txs if t.shared_sink) == 4
    assert Counter(t.actor_index for t in plan.txs) == {0: 3, 1: 3, 2: 3, 3: 3}

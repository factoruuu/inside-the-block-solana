import pytest

from itb.stats import pairwise_concordance, spearman


def test_concordance_perfect_agreement():
    # Higher fee always lands earlier (smaller index -> larger -index).
    fees = [0, 10, 20, 30]
    neg_index = [-30, -20, -10, 0]  # fee 30 at index 0, fee 0 at index 30
    res = pairwise_concordance([float(f) for f in fees], [float(v) for v in neg_index])
    assert res["fraction"] == 1.0
    assert res["discordant"] == 0


def test_concordance_perfect_disagreement():
    fees = [0, 10, 20, 30]
    neg_index = [0, -10, -20, -30]  # highest fee lands LAST
    res = pairwise_concordance([float(f) for f in fees], [float(v) for v in neg_index])
    assert res["fraction"] == 0.0


def test_concordance_ties_excluded():
    # Outcome is -block_index: the fee-9 tx landed earliest (largest -index=0),
    # so both non-tied pairs are concordant; the equal-fee pair is tied.
    res = pairwise_concordance([5.0, 5.0, 9.0], [-2.0, -1.0, 0.0])
    assert res["tied"] == 1  # the equal-fee pair
    assert res["fraction"] == 1.0


def test_concordance_known_value():
    # Pairs: (1,2) agree, (1,3) agree, (2,3) disagree -> 2/3.
    res = pairwise_concordance([1.0, 2.0, 3.0], [1.0, 3.0, 2.0])
    assert res["concordant"] == 2 and res["discordant"] == 1
    assert res["fraction"] == pytest.approx(2 / 3)


def test_spearman_perfect_and_inverse():
    assert spearman([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)
    assert spearman([1, 2, 3, 4], [40, 30, 20, 10]) == pytest.approx(-1.0)


def test_spearman_handles_ties_and_degenerate():
    assert spearman([1, 1, 2], [1, 2, 3]) is not None
    assert spearman([5, 5, 5], [1, 2, 3]) is None
    assert spearman([1], [2]) is None

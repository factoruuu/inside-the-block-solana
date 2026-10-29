import pytest

from itb.ledger import SpendCapExceeded, SpendLedger


def test_cap_enforcement(tmp_path):
    ledger = SpendLedger.load(tmp_path / "ledger.json", cap_lamports=10_000)
    ledger.check_can_spend(6_000)
    ledger.record_sent("sig1", 6_000, "burst-a")
    assert ledger.spent_lamports == 6_000
    assert ledger.remaining_lamports == 4_000
    with pytest.raises(SpendCapExceeded):
        ledger.check_can_spend(4_001)
    # Exactly at the cap is allowed.
    ledger.check_can_spend(4_000)


def test_ledger_persists_and_counts_only_recorded(tmp_path):
    path = tmp_path / "ledger.json"
    ledger = SpendLedger.load(path, cap_lamports=50_000_000)
    ledger.record_sent("sigA", 5_250, "b1")
    ledger.record_sent("sigB", 5_000, "b1")
    reloaded = SpendLedger.load(path, cap_lamports=50_000_000)
    assert reloaded.spent_lamports == 10_250
    assert len(reloaded.entries) == 2


def test_ledger_rejects_cap_change(tmp_path):
    path = tmp_path / "ledger.json"
    SpendLedger.load(path, cap_lamports=100).record_sent("s", 1, "b")
    with pytest.raises(ValueError):
        SpendLedger.load(path, cap_lamports=200)


def test_default_cap_matches_brief():
    from itb.config import DEFAULT_SPEND_CAP_LAMPORTS

    assert DEFAULT_SPEND_CAP_LAMPORTS == 50_000_000  # 0.05 SOL

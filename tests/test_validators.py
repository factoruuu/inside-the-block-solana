import pytest

from itb.validators import classify_client, join_validators, select_validators


@pytest.mark.parametrize(
    "version,expected",
    [
        ("2.1.7", "agave"),
        ("3.0.1", "agave"),
        ("2.1.7-jito", "jito"),
        ("1.18.26-jito", "jito"),
        ("0.114.20414", "frankendancer/firedancer"),
        (None, "unknown"),
        ("", "unknown"),
    ],
)
def test_classify_client(version, expected):
    assert classify_client(version) == expected


@pytest.mark.parametrize(
    "client_id,expected",
    [
        ("Agave", "agave"),
        ("JitoLabs", "jito"),
        ("AgaveBam", "agave-bam"),
        ("Firedancer", "firedancer"),
        ("Frankendancer", "frankendancer"),
        ("HarmonicFiredancer", "harmonic-firedancer"),
    ],
)
def test_classify_client_prefers_client_id(client_id, expected):
    # Live mainnet: Agave, Jito and AgaveBam all report version "4.3.2";
    # only clientId separates them.
    assert classify_client("4.3.2", client_id) == expected


def test_classify_client_unknown_client_id_falls_back_to_version():
    assert classify_client("2.1.7", "Unknown(42)") == "agave"


def _fake_cluster(n_per_client=3):
    vote = {"current": []}
    nodes = []
    versions = {"agave": "2.1.7", "jito": "2.1.7-jito", "fd": "0.114.20414"}
    stake = 10_000_000
    for label, ver in versions.items():
        for i in range(n_per_client):
            vote["current"].append(
                {"votePubkey": f"vote-{label}-{i}", "nodePubkey": f"node-{label}-{i}", "activatedStake": stake}
            )
            nodes.append({"pubkey": f"node-{label}-{i}", "version": ver, "gossip": "127.0.0.1:8000"})
            stake -= 100
    return vote, nodes


def test_selection_meets_brief_minimums():
    vote, nodes = _fake_cluster()
    validators = join_validators(vote, nodes)
    selected = select_validators(validators, min_validators=6, min_client_classes=3)
    assert len(selected) >= 6
    assert len({v.client for v in selected}) >= 3


def test_selection_fails_when_too_few_classes():
    vote, nodes = _fake_cluster()
    nodes = [n for n in nodes if "jito" not in n["pubkey"] and "fd" not in n["pubkey"]]
    validators = join_validators(vote, nodes)
    with pytest.raises(ValueError):
        select_validators(validators, min_validators=6, min_client_classes=3)

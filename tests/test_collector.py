from itb.collector import block_metadata, extract_positions


def canned_block():
    return {
        "blockTime": 1761696000,
        "blockHeight": 300000000,
        "parentSlot": 999,
        "transactions": [
            {"transaction": {"signatures": ["foreignA"]}},
            {"transaction": {"signatures": ["ours1", "extra"]}},
            {"transaction": {"signatures": ["foreignB"]}},
            {"transaction": {"signatures": ["ours2"]}},
        ],
    }


def test_extract_positions():
    positions = extract_positions(canned_block(), {"ours1", "ours2", "notInBlock"})
    assert positions == {"ours1": 1, "ours2": 3}


def test_extract_positions_empty():
    assert extract_positions(canned_block(), set()) == {}
    assert extract_positions({"transactions": []}, {"x"}) == {}


def test_block_metadata():
    meta = block_metadata(canned_block(), slot=1000, leader="LeaderPubkey")
    assert meta["tx_count"] == 4
    assert meta["slot"] == 1000
    assert meta["leader"] == "LeaderPubkey"
    assert meta["block_time"] == 1761696000

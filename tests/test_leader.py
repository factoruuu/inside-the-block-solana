from itb.leader import LeaderWindow, epoch_start_slot, find_windows, invert_schedule


def test_invert_schedule_applies_epoch_offset():
    # getLeaderSchedule slots are epoch-relative (verified live on mainnet).
    schedule = {"LeaderA": [0, 1, 2, 3], "LeaderB": [4, 5, 6, 7]}
    inv = invert_schedule(schedule, epoch_start_slot=432_000)
    assert inv[432_000] == "LeaderA"
    assert inv[432_007] == "LeaderB"
    assert len(inv) == 8


def test_epoch_start_slot():
    assert epoch_start_slot({"absoluteSlot": 462_743_254, "slotIndex": 311_254}) == 462_432_000


def test_find_windows_requires_aligned_full_window():
    inv = {}
    for s in range(100, 116):
        inv[s] = "LeaderA" if s < 108 else "LeaderB"
    windows = find_windows(inv, "LeaderA", after_slot=100)
    assert [w.start_slot for w in windows] == [100, 104]
    assert windows[0].slots == [100, 101, 102, 103]
    # LeaderB starts mid-alignment at 108 (aligned) — one full window only.
    assert [w.start_slot for w in find_windows(inv, "LeaderB", after_slot=100)] == [108, 112]
    assert find_windows(inv, "Nobody", after_slot=100) == []

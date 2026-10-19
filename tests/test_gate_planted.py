"""Throwaway: proves CI rejects a failing unit test. Never merge."""


def test_planted_failure():
    assert 1 == 2, "planted failure for the Phase 0 gate"

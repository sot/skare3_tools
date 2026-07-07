"""
Characterize the json_cache decorator (skare3_tools/packages.py:110-212).

Key current behavior these tests pin:
- The wrapper adds an ``update=False`` kwarg to the decorated function.
- A cold call (no cache file, update=False) runs the function every time and
  does NOT persist a cache file. Only ``update=True`` writes the file.
- Once written, subsequent calls are served from the file.
- An ``expires`` interval refreshes (re-runs + rewrites) a stale cache entry.
"""

import os

from skare3_tools.config import CONFIG
from skare3_tools.packages import json_cache


def _counting(name, **cache_kwargs):
    calls = {"n": 0}

    @json_cache(name, **cache_kwargs)
    def fn():
        calls["n"] += 1
        return {"value": calls["n"]}

    return fn, calls


def _cache_file(name):
    return os.path.join(CONFIG["data_dir"], f"{name}::.json")


def test_cold_call_does_not_persist():
    fn, calls = _counting("t_cold")
    assert fn() == {"value": 1}
    assert fn() == {"value": 2}          # no file -> function runs again
    assert calls["n"] == 2
    assert not os.path.exists(_cache_file("t_cold"))


def test_update_writes_and_hits():
    fn, calls = _counting("t_update")
    assert fn(update=True) == {"value": 1}
    assert os.path.exists(_cache_file("t_update"))
    assert fn() == {"value": 1}          # served from file
    assert calls["n"] == 1


def test_expiry_refreshes():
    fn, calls = _counting("t_expiry", expires={"days": 1})
    fn(update=True)
    two_days_ago = os.path.getmtime(_cache_file("t_expiry")) - 2 * 86400
    os.utime(_cache_file("t_expiry"), (two_days_ago, two_days_ago))
    assert fn() == {"value": 2}          # stale -> function re-runs
    assert calls["n"] == 2
    # and the file was rewritten (fresh mtime)
    assert os.path.getmtime(_cache_file("t_expiry")) - two_days_ago > 86400

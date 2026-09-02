"""
The release-notes summary (skare3_tools/scripts/skare3_update_summary.py).

Behavior pinned: when the initial version is outside the release window the
store holds, the summary asks Github for exactly the history it needs --
``since=<the initial version>`` -- rather than a fixed, much larger window.
The merges of every release in the range end up in the summary.
"""

import pytest

from skare3_tools import packages
from skare3_tools.scripts import skare3_update_summary

PACKAGE_LIST = [
    {"name": "foo", "package": "foo", "repository": "sot/foo", "owner": "sot"}
]


def _release(tag, pr=None):
    merges = [{"pr_number": pr, "title": f"PR {pr}", "author": "someone"}] if pr else []
    return {"release_tag": tag, "merges": merges}


# what the store holds: the window reaches back only to 1.2.0
STORED = {
    "owner": "sot",
    "name": "foo",
    "release_info": [_release(""), _release("1.2.0", pr=22)],
}

# what Github returns when asked to look back to 1.0.0
DEEP = {
    "owner": "sot",
    "name": "foo",
    "release_info": [
        _release(""),
        _release("1.2.0", pr=22),
        _release("1.1.0", pr=11),
        _release("1.0.0"),
    ],
}


@pytest.fixture()
def github_calls(monkeypatch):
    calls = []

    def fake_get_repository_info(owner_repo, **kwargs):
        calls.append((owner_repo, kwargs))
        return DEEP

    monkeypatch.setattr(packages, "get_package_list", lambda: list(PACKAGE_LIST))
    monkeypatch.setattr(packages, "get_repository_info", fake_get_repository_info)
    return calls


def test_missing_initial_version_asks_for_exactly_that_history(github_calls):
    summary = skare3_update_summary.repository_change_summary(
        [STORED], {"foo": "1.0.0"}, {"foo": "1.2.0"}
    )

    # the escalation names the version it needs, not a fixed release count
    assert github_calls == [("sot/foo", {"since": "1.0.0"})]

    (update,) = summary["updates"]
    assert update["versions"] == ["1.0.0", "1.1.0", "1.2.0"]
    assert [merge["PR"] for merge in update["merges"]] == [11, 22]


def test_no_escalation_when_the_stored_window_is_enough(github_calls):
    summary = skare3_update_summary.repository_change_summary(
        [STORED], {"foo": "1.2.0"}, {"foo": "1.2.0"}
    )
    assert github_calls == []
    assert summary["updates"] == []

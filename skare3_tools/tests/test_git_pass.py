"""
Tests for the GIT_ASKPASS helper (skare3_tools/scripts/git_pass.py).

Git invokes the helper with its full prompt string as the single argument,
e.g. ``git_pass.py "Username for 'https://github.com': "``, so the script
must match on substrings of the prompt, not on literal words.
"""

import sys

import pytest

from skare3_tools.scripts import git_pass


@pytest.fixture(autouse=True)
def credentials(monkeypatch):
    monkeypatch.setenv("GIT_USERNAME", "chandra-xray")
    monkeypatch.setenv("GIT_PASSWORD", "s3cret")


def run_main(monkeypatch, prompt):
    monkeypatch.setattr(sys, "argv", ["git_pass.py", prompt])
    git_pass.main()


def test_git_username_prompt(monkeypatch, capsys):
    run_main(monkeypatch, "Username for 'https://github.com': ")
    assert capsys.readouterr().out == "chandra-xray\n"


def test_git_password_prompt(monkeypatch, capsys):
    run_main(monkeypatch, "Password for 'https://chandra-xray@github.com': ")
    assert capsys.readouterr().out == "s3cret\n"


def test_bare_username(monkeypatch, capsys):
    run_main(monkeypatch, "username")
    assert capsys.readouterr().out == "chandra-xray\n"


def test_bare_password(monkeypatch, capsys):
    run_main(monkeypatch, "password")
    assert capsys.readouterr().out == "s3cret\n"


def test_unrelated_prompt_prints_nothing(monkeypatch, capsys):
    run_main(monkeypatch, "Passphrase for key '/home/user/.ssh/id_rsa': ")
    assert capsys.readouterr().out == ""

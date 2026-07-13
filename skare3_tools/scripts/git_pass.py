#!/usr/bin/env python
"""
Utility script to provide username/password when authenticating git.

This script reads the GIT_USERNAME and GIT_PASSWORD environmental variables
and returns the corresponding value when requested.

If one sets the GIT_ASKPASS environmental variable to point to this script, and sets GIT_USERNAME
and GIT_PASSWORD, git takes care of the rest.
"""

import argparse
from os import environ


def parser():
    parse = argparse.ArgumentParser(description=__doc__)
    parse.add_argument(
        "prompt",
        help="The prompt from git, e.g. \"Username for 'https://github.com': \".",
    )
    return parse


def main():
    args = parser().parse_args()
    prompt = args.prompt.lower()
    if "username" in prompt:
        print(environ["GIT_USERNAME"])
    elif "password" in prompt:
        print(environ["GIT_PASSWORD"])


if __name__ == "__main__":
    main()

#!/usr/bin/env python
"""
Utility script to provide username/password when authenticating git.
This script reads the GIT_USERNAME and GIT_PASSWORD environmental variables
and returns the corresponding value when requested.

If one sets the GIT_ASKPASS environmental variable to point to this script, and sets GIT_USERNAME
and GIT_PASSWORD, git takes care of the rest.
"""

from os import environ
import argparse


def parser():
    parse = argparse.ArgumentParser(description=__doc__)
    parse.add_argument('what', help="What is being requested (either password or username).",
                       choices=['username', 'password'])
    return parse


def main():
    args = parser().parse_args()
    if args.what.lower() == 'username':
        print(environ['GIT_USERNAME'])
    elif args.what.lower() == 'password':
        print(environ['GIT_PASSWORD'])


if __name__ == '__main__':
    main()

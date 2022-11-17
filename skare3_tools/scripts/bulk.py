#!/usr/bin/env python3
"""
Script to run the same command in a collection of subdirectories.
"""
import argparse
import subprocess


def parser():
    parse = argparse.ArgumentParser(description=__doc__)
    parse.add_argument("cmd", help="The command to run", nargs="+")
    parse.add_argument(
        "--repositories",
        help="the name of the subdirectories",
        default="git_repositories",
    )
    return parse


def main():
    args, extra = parser().parse_known_args()
    args.cmd += extra
    packages = [line.strip() for line in open(args.repositories).readlines()]
    for package in packages:
        header = f"\n\n{package}\n{'-'*len(package)}" ""
        print(header)
        try:
            subprocess.check_call(args.cmd, cwd=package)
        except Exception as e:
            print("fail", e)


if __name__ == "__main__":
    main()

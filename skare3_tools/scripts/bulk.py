#!/usr/bin/env python3

import argparse
import subprocess

def parser():
    parse = argparse.ArgumentParser()
    parse.add_argument('cmd', nargs='+')
    parse.add_argument('--repositories', default='git_repositories')
    return parse

def main():
    args, extra = parser().parse_known_args()
    args.cmd += extra
    packages = [l.strip() for l in open(args.repositories).readlines()]
    for package in packages:
        header = f"\n\n{package}\n{'-'*len(package)}"""
        print(header)
        try:
            subprocess.check_call(args.cmd, cwd=package)
        except Exception as e:
            print('fail', e)

if __name__ == '__main__':
    main()

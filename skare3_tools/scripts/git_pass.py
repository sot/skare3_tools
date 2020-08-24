#!/usr/bin/env python

from sys import argv
from os import environ


def main():
    if 'username' in argv[1].lower():
        print(environ['GIT_USERNAME'])

    if 'password' in argv[1].lower():
        print(environ['GIT_PASSWORD'])


if __name__ == '__main__':
    main()

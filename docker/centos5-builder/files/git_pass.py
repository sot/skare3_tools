#!/usr/bin/env python3

from os import environ
from sys import argv

if "username" in argv[1].lower():
    print(environ["GIT_USERNAME"])

if "password" in argv[1].lower():
    print(environ["GIT_PASSWORD"])

#!/usr/bin/env python3
"""
A script to add encrypted secrets to Github repositories.

At this moment, Github's API does not have an endpoint for setting secrets.
This script circumvents this limitation by using
`Selenium with Python <https://selenium-python.readthedocs.io/>`_
together with `ChromeDriver <https://sites.google.com/a/chromium.org/chromedriver>`.

To use it, you need to have Chrome installed,
`install Selenium <https://selenium-python.readthedocs.io/installation.html>`_, and you need to get
`a version of ChromeDriver <https://sites.google.com/a/chromium.org/chromedriver/downloads>`_
matching your Chrome version. I suppose it could work with other browsers but I have not tried it.

A valid YAML file looks like this:

   SECRET_NAME: the secret value

   SECRET_TWO: |
      another value
      asdf

"""


import json
import yaml
import time
import os
import sys
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
import getpass
import keyring
import argparse

_driver_ = None


def go(url, allow_timeout=True, ok=None, verbose=False, max_tries=5):
    """
    get one URL. Try max_tries before throwing.
    """
    for i in range(max_tries+1):
        if i > max_tries:
            raise Exception()
        try:
            _driver_.get(url)
            time.sleep(2)
            break
        except TimeoutException:
            if ok is not None and not ok():
                if verbose:
                    print(url, 'time out fail')
                continue
            if allow_timeout:
                if verbose:
                    print(url, 'time out')
                break
        except Exception as e:
            if verbose:
                print(url, 'timeout', str(e))


def init():
    global _driver_
    _driver_ = webdriver.Chrome('chromedriver')
    _driver_.implicitly_wait(20)
    _driver_.set_page_load_timeout(20)


def login(username, password=None):
    global _driver_
    if _driver_ is None:
        init()

    if password is None:
        if 'GITHUB_PASSWORD' in os.environ:
            password = os.environ['GITHUB_PASSWORD']
        elif keyring:
            password = keyring.get_password("skare3-github", username)
        if password is None:
            password = getpass.getpass()

    go('https://github.com/login')
    _driver_.find_element_by_id('login_field').send_keys(username)
    _driver_.find_element_by_id('password').send_keys(password)
    _driver_.find_element_by_name('commit').click()


def add_secrets(repository, secrets):
    go(f'https://github.com/{repository}/settings/secrets')

    for secret in secrets:
        buttons = _driver_.find_elements_by_tag_name('button')

        button = [button for button in buttons if button.text == 'Add a new secret'][0]
        button.click()

        _driver_.find_element_by_id('name').send_keys(secret)
        value = secrets[secret]
        if type(value) == dict:
            value = json.dumps(value)
        _driver_.find_element_by_id('secret_value').send_keys(value)
        button = [button for button in buttons if button.text == 'Add secret'][0]
        button.click()


def parser():
    parse = argparse.ArgumentParser(description=__doc__)
    parse.add_argument('repositories', nargs='+')
    parse.add_argument('--secrets', default='secrets.json', help='JSON file with all secrets')
    parse.add_argument('--user', required=True, help='Github user name')
    parse.add_argument('--no-quit', dest='quit', default=True, action='store_false',
                       help='Do not close chrome browser at the end')
    return parse


def main():
    global _driver_
    args = parser().parse_args()

    with open(args.secrets) as f:
        if args.secrets[-4:] in ['.yaml', '.yml']:
            # secrets = yaml.load(f, Loader=yaml.FullLoader)
            secrets = yaml.load(f)
        elif args.secrets[-5:] == '.json':
            secrets = json.load(f)
        else:
            print(f"don't know how to handle file '{args.secrets}'")
            sys.exit(1)

    try:
        login(args.user)
        for repository in args.repositories:
            print(repository)
            try:
                add_secrets(repository, secrets)
            except Exception as e:
                print(f' - Failed setting {repository} secrets: {e}')
    except Exception as e:
        print(f'Failed setting secrets: {e}')
    finally:
        if args.quit:
            _driver_.quit()
            _driver_ = None


if __name__ == '__main__':
    main()
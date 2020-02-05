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


import json, sys, time, os
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException
import getpass
import keyring
import yaml
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
            if not ok is None and not ok():
                if verbose: print(url, 'time out fail')
                continue
            if allow_timeout:
                if verbose: print(url, 'time out')
                break
        except Exception as e:
            if verbose: print(url, 'timeout', str(e))


def init():
    global _driver_
    _driver_ = webdriver.Chrome('chromedriver')
    _driver_.implicitly_wait(20)
    _driver_.set_page_load_timeout(20)


def login(username, password=None):
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

        # this is not strictly needed it just shows th input fields that are hidden by default:
        try:
            button = [button for button in buttons if button.text == 'Add a new secret'][0]
            button.click()
        except Exception as e:
            pass

        _driver_.find_element_by_id('name').send_keys(secret)
        _driver_.find_element_by_id('secret_value').send_keys(str(secrets[secret]))
        button = [button for button in buttons if button.text == 'Add secret'][0]
        button.click()


def parser():
    parse = argparse.ArgumentParser(description=__doc__)
    parse.add_argument('repositories', nargs='+')
    parse.add_argument('--secrets', default='secrets.yml', help='YAML file with all secrets')
    parse.add_argument('--user', required=True, help='Github user name')
    return parse


def main():
    args = parser().parse_args()

    with open(args.secrets) as f:
        #secrets = yaml.load(f, Loader=yaml.FullLoader)
        secrets = yaml.load(f)
    login(args.user)
    for repository in args.repositories:
        add_secrets(repository, secrets)


if __name__ == '__main__':
    main()

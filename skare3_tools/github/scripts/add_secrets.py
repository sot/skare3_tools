#!/usr/bin/env python3
"""
A script to add encrypted secrets to Github repositories.

At some point, Github's API did not have an endpoint for setting secrets.
This script circumvented this limitation by using
`Selenium with Python <https://selenium-python.readthedocs.io/>`_
together with `ChromeDriver <https://sites.google.com/a/chromium.org/chromedriver>`. While this is
not strictly needed anymore, it is left because it is an example on how to deal with cases like
this.


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


import argparse
import getpass
import json
import logging
import os
import sys
import time
from urllib.parse import urlparse

import yaml

_driver_ = None


def go(url, allow_timeout=True, ok=None, verbose=False, max_tries=5):
    """
    get one URL. Try max_tries before throwing.
    """
    from selenium.common.exceptions import TimeoutException

    for i in range(max_tries + 1):
        if i > max_tries:
            raise Exception()
        try:
            _driver_.get(url)
            time.sleep(2)
            break
        except TimeoutException:
            if ok is not None and not ok():
                if verbose:
                    print(url, "time out fail")
                continue
            if allow_timeout:
                if verbose:
                    print(url, "time out")
                break
        except Exception as e:
            if verbose:
                print(url, "timeout", str(e))


def init():
    from selenium import webdriver

    global _driver_
    _driver_ = webdriver.Chrome("chromedriver")
    _driver_.implicitly_wait(20)
    _driver_.set_page_load_timeout(20)


def login(username, password=None):
    global _driver_
    if _driver_ is None:
        init()

    if password is None:
        if "GITHUB_PASSWORD" in os.environ:
            password = os.environ["GITHUB_PASSWORD"]
        else:
            try:
                import keyring

                password = keyring.get_password("skare3-github", username)
            except ModuleNotFoundError:
                pass
            except keyring.errors.KeyringLocked:
                pass
        if password is None:
            password = getpass.getpass(f"Password for {username}:")

    go("https://github.com/login")
    _driver_.find_element_by_id("login_field").send_keys(username)
    _driver_.find_element_by_id("password").send_keys(password)
    _driver_.find_element_by_name("commit").click()

    # this can be improved if I ever use it heavily.
    if urlparse(_driver_.current_url).path == "/sessions/two-factor":
        wait = 30
        logging.warning(
            f"two-factor authentication. Waiting {wait} seconds before proceeding"
        )
        import time

        time.sleep(wait)

    meta = _driver_.find_elements_by_tag_name("meta")
    meta = [m for m in meta if m.get_attribute("name") == "user-login"]
    username = meta[0].get_attribute("content")
    if not username:
        raise Exception("Login failed")
    logging.info(f"logged in as {username}")


def _get_button(text):
    buttons = _driver_.find_elements_by_tag_name("button")
    button = [button for button in buttons if button.text == text]
    if not button:
        raise Exception(f'Unexpected format: No "{text}" button')
    if len(buttons) > 1:
        logging.warning(f'More than one "{text}" button')
    return button[0]


def _get_link(text=None, **attributes):
    links = _driver_.find_elements_by_tag_name("a")
    if text is not None:
        links = [line for line in links if line.text == text]
    for att in attributes:
        links = [line for line in links if line.get_attribute(att) == attributes[att]]
    msg = f"link with attributes={attributes}"
    if text is not None:
        msg += f" and text={text}"
    if len(links) == 0:
        raise Exception(f"No {msg}")
    if len(links) > 1:
        logging.warning(f"More than one {msg}")
    return links[0]


def add_secrets(repository, secrets):
    go(f"https://github.com/{repository}/settings/secrets")

    for secret in secrets:
        _get_link(text="New secret", role="button").click()

        _driver_.find_element_by_id("secret_name").send_keys(secret)
        value = secrets[secret]
        if type(value) == dict:
            value = json.dumps(value)
        _driver_.find_element_by_id("secret_value").send_keys(value)

        _get_button("Add secret").click()


def parser():
    parse = argparse.ArgumentParser(description=__doc__)
    parse.add_argument("repositories", nargs="+")
    parse.add_argument(
        "--secrets", default="secrets.json", help="JSON file with all secrets"
    )
    parse.add_argument("--user", required=True, help="Github user name")
    parse.add_argument(
        "--no-quit",
        dest="quit",
        default=True,
        action="store_false",
        help="Do not close chrome browser at the end",
    )
    return parse


def main():
    global _driver_
    the_parser = parser()
    args = the_parser.parse_args()

    try:
        import selenium  # noqa
    except ModuleNotFoundError:
        logging.error(
            f"The script requires the selenium module. Run `{sys.argv[0]} -h` for help."
        )
        the_parser.exit(2)

    if not os.path.exists(args.secrets):
        logging.error(
            f"The secrets file {args.secrets} does not exist. "
            f"Run `{sys.argv[0]} -h` for help."
        )
        the_parser.exit(3)

    with open(args.secrets) as f:
        if args.secrets[-4:] in [".yaml", ".yml"]:
            secrets = yaml.load(f, Loader=yaml.FullLoader)
        elif args.secrets[-5:] == ".json":
            secrets = json.load(f)
        else:
            logging.error(f"don't know how to handle file '{args.secrets}'")
            sys.exit(1)

    try:
        login(args.user)
        for repository in args.repositories:
            print(repository)
            try:
                add_secrets(repository, secrets)
            except Exception as e:
                print(f" - Failed setting {repository} secrets: {e}")
    except Exception as e:
        print(f"Failed setting secrets: {e}")
    finally:
        if _driver_ is not None and args.quit:
            _driver_.quit()
            _driver_ = None


if __name__ == "__main__":
    main()

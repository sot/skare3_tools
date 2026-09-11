"""
A wrapper for Github's APIs and a collection of scripts.

In order to use it, one needs to give it an `authentication token`_. The token is usually given
using the GITHUB_API_TOKEN environmental variable. You can optionally initialize the API with a
given token::

    >>> from skare3_tools import github
    >>> github.init(token='c7hvg6pqi3fhqwv0wvlgp4mk9agwbqk1gxc331iz')  # this is optional

Importing this module never accesses the network: credentials are only read from the
environment, and they are checked when :func:`init` is called or when the API is used.
A missing or stale token therefore does not stop a program that ends up not querying
Github.

.. _`authentication token`: https://docs.github.com/en/authentication
"""

from . import github, graphql
from .github import Organization, Repository  # noqa: F401

GITHUB_API_V3 = github.GITHUB_API
GITHUB_API_V4 = graphql.GITHUB_API


def init(token=None):
    GITHUB_API_V3.init(token=token, force=True)
    GITHUB_API_V4.init(token=token, force=True)

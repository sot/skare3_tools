from .github import Repository

from . import graphql, github

GITHUB_API_V3 = github.GITHUB_API
GITHUB_API_V4 = graphql.GITHUB_API


def init(token=None):
    GITHUB_API_V3.init(token=token, force=True)
    GITHUB_API_V4.init(token=token, force=True)

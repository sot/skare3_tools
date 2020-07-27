from .github import *

from . import graphql

GITHUB_API_V3 = None
GITHUB_API_V4 = None


def init(token=None):
    global GITHUB_API_V3
    global GITHUB_API_V4
    from . import github, graphql
    GITHUB_API_V3 = github.init(token, force=True)
    GITHUB_API_V4 = graphql.init(token, force=True)

init()
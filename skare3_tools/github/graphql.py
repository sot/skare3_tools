"""
This is a thin wrapper for `Github's GraphQL API`_.
Given the flexibility of the GraphQL interface, this module is a collection of standard queries.

.. _`Github's REST API`: https://developer.github.com/v4/

"""

import os
import logging
import requests

class GithubException(Exception):
    pass

_logger = logging.getLogger('github')
GITHUB_API = None


# The following is a general query to get information about a repository
# To write new queries, the best is to go to https://developer.github.com/v4/explorer/
# and experiment a bit
REPO_QUERY = """
{
  repository(name: "{{ name }}", owner: "{{ owner }}") {
    name
    owner {
      login
    }
    refs(refPrefix: "refs/", first: 100) {
      totalCount
      nodes {
        name
        associatedPullRequests(first: 100) {
          nodes {
            number
            title
            headRefName
            baseRefName
            state
            mergeCommit {
              oid
              message
            }
          }
          pageInfo {
            hasNextPage
            endCursor
          }
        }
      }
      pageInfo {
        endCursor
        hasNextPage
      }
    }
    releases(first: 100) {
      totalCount
      nodes {
        name
        tagName
        createdAt
        publishedAt
        isPrerelease
        isDraft
        id
        url
        tag {
          id
        }
      }
      pageInfo {
        endCursor
        hasNextPage
      }
    }
  }
}

"""

REPO_ISSUES_QUERY = """
{
  repository(name: "{{ name }}", owner: "{{ owner }}") {
    name
    owner {
      login
    }
    issues(first: 100, states: OPEN, labels: {{ label }}) {
      nodes {
        author {
          login
        }
        closed
        number
        state
        title
        milestone {
          title
        }
      }
      pageInfo {
        hasNextPage
        endCursor
      }
    }
  }
}
"""

REPO_PR_QUERY = """
{
  repository(name: "{{ name }}", owner: "{{ owner }}") {
    name
    owner {
      login
    }
    pullRequests(first: 100, baseRefName: "master") {
      nodes {
        baseRefName
        headRefName
        title
        number
        state
      }
      pageInfo {
        hasNextPage
        endCursor
      }
    }
  }
}
"""

ORG_QUERY = """
{
  organization(login: "{{ owner }}") {
    repositories(first:100) {
      nodes {
        name
        nameWithOwner
        owner {
          login
        }
      }
      pageInfo {
        hasNextPage
        endCursor
      }
    }
  }
}
"""

RATE_LIMIT_QUERY = """
{
  viewer {
    login
  }
  rateLimit {
    limit
    cost
    remaining
    resetAt
  }
}
"""

def init(token=None):
    """
    Initialize the Github API.

    :param token: str
    :return: GithubAPI
    """
    global GITHUB_API
    if GITHUB_API is None:
        if token is not None:
            api = GithubAPI(token=token)
        elif 'GITHUB_TOKEN' in os.environ:
            api = GithubAPI(token=os.environ['GITHUB_TOKEN'])
        else:
            raise GithubException('Github token needs to be given as argument '
                                  'or set in GITHUB_TOKEN environment variable')
        response = api('{viewer {login}}')
        GITHUB_API = api
        user = response['data']['viewer']['login']
        _logger.info(f'Github interface initialized (user={user})')
    return GITHUB_API


class GithubAPI:
    """
    Main class that encapsulates Github's REST API.
    """
    def __init__(self, token=None):
        self.token = token
        self.headers = {"Authorization": f"token {token}"}
        self.api_url = 'https://api.github.com/graphql'

    @staticmethod
    def check(response):
        if not response.ok:
            raise GithubException(f'Error: {response.reason} ({response.status_code})')

    def __call__(self, query, headers=(), **kwargs):
        _headers = self.headers.copy()
        _headers.update(headers)
        response = requests.request('post', self.api_url, headers=_headers, json={'query': query},
                                    **kwargs)

        if not response.ok:
            raise GithubException(f'Error: {response.reason} ({response.status_code})')

        return response.json()

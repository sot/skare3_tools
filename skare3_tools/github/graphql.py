"""
This is a thin wrapper for `Github's GraphQL API`_ (V4).

This module does not build the query for you. This is because the possibilities afforded by GraphQL
are large and it makes no sense to re-invent them. The easiest way to assemble a new query is to use
`Github's GraphQL Explorer`_. For example, to get the homepage URL of a repository:

.. code-block:: python

    >>> from skare3_tools.github import graphql
    >>> query = \"""{
    ...   repository(name: "test-actions", owner: "sot") {
    ...     homepageUrl
    ...     id
    ...   }
    ... }\"""
    >>> response = graphql.GITHUB_API(query)
    >>> response
    {'data': {'repository': {'homepageUrl': None,
    'id': 'MDEwOlJlcG9zaXRvcnkyMDkwMjE1NDQ='}}}

and to set the homepage URL of a repository:

    >>> from skare3_tools.github import graphql
    >>> query = \"""mutation {
    ...   updateRepository(input: {repositoryId: "MDEwOlJlcG9zaXRvcnkyMDkwMjE1NDQ=",
    ...                             homepageUrl: "https://github.com/sot/test-actions"})
    ...   {
    ...     repository {
    ...       id
    ...       homepageUrl
    ...     }
    ...   }
    ... }
    ... \"""
    >>> response = graphql.GITHUB_API(query)
    >>> response
    {'data': {'updateRepository': {'repository': {'id': 'MDEwOlJlcG9zaXRvcnkyMDkwMjE1NDQ=',
    'homepageUrl': 'https://github.com/sot/test-actions'}}}}



Given the flexibility of the GraphQL interface, this module includes a small collection of common
queries. Each query in the collection is a string that should be used as a jinja2 template. For
example, to get a list all pull requests of a repository:

.. code-block:: python

    >>> import jinja2
    >>> from skare3_tools.github import graphql
    >>> query = jinja2.Template(graphql.REPO_PR_QUERY).render(owner='sot', name='Quaternion')
    >>> response = graphql.GITHUB_API(query)
    >>> response['data']['repository']['pullRequests']['nodes'][0]
    {'baseRefName': 'master',
     'headRefName': 'modernize',
     'title': 'Add delta quaternion method and other package modernization',
     'number': 2,
     'state': 'MERGED'}

THere is a (possibly incomplete) list of queries (with the template parameters in parentheses):

- REPO_ISSUES_QUERY(name, owner, label)
- REPO_PR_QUERY(name, owner)
- ORG_QUERY(owner)
- REPO_QUERY(owner, name)

.. _`Github's GraphQL API`: https://developer.github.com/v4/
.. _`Github's GraphQL Explorer`: https://developer.github.com/v4/explorer/

"""

import os
import logging
import requests

class GithubException(Exception):
    pass

class AuthException(Exception):
    pass


_logger = logging.getLogger('github')


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
"""query all issues in repository (name, owner, label)"""

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
"""query all pull requests in repository (name, owner)"""

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
"""query all repositories in an organization (owner)"""

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
    pushedAt
    updatedAt
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
          target {
            ... on Commit {
              oid
            }
            ... on Tag {
              oid
              target {
                ... on Commit {
                  oid
                }
                ... on Tag {
                  oid
                  target {
                    ... on Commit {
                      oid
                    }
                  }
                }
              }
            }
          }
        }
      }
      pageInfo {
        endCursor
        hasNextPage
      }
    }
    pullRequests(last: 100) {
      nodes {
        number
        title
        url
        commits(last: 100) {
          totalCount
          nodes {
            commit {
              committedDate
              pushedDate
              message
            }
          }
        }
        baseRefName
        headRefName
        state
      }
      pageInfo {
        hasPreviousPage
        hasNextPage
        startCursor
        endCursor
      }
    }
    issues(first: 100, states: OPEN) {
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
    defaultBranchRef {
      name
      target {
        ... on Commit {
          history(first: 100) {
            pageInfo {
              hasNextPage
              endCursor
            }
            nodes {
              oid
              message
            }
          }
        }
      }
    }
  }
}

"""
"""A general query to get information about a repository (owner, name)"""


def init(token=None, force=True):
    """
    Initialize the API.

    :param token: str
        a Github auth token
    :param force: bool
        override a previously initialized API
    :return:
    """
    GITHUB_API.init(token, force)
    return GITHUB_API


class GithubAPI:
    """
    Main class that encapsulates Github's GraphQL API.
    """
    def __init__(self, token=None):
        self.initialized = False
        self.headers = None
        self.api_url = 'https://api.github.com/graphql'
        try:
            self.init(token)
        except AuthException:
            # the exception is not raised if we are creating the API with default args.
            # An exception will be raised later, when one tries to use it.
            if token is not None:
                raise

    def __bool__(self):
        """
        Returns True if API is initialized.

        :return: bool
        """
        return self.initialized

    def init(self, token=None, force=True):
        """
        Initialize the Github API.

        :param token: str
        :param force: bool
        :return: GithubAPI
        """
        if self.initialized and not force:
            return

        if token is not None:
            token = os.path.expandvars(token)
        elif 'GITHUB_API_TOKEN' in os.environ:
            token = os.path.expandvars(os.environ['GITHUB_API_TOKEN'])
        elif 'GITHUB_TOKEN' in os.environ:
            token = os.path.expandvars(os.environ['GITHUB_TOKEN'])
        else:
            raise AuthException('Bad credentials. '
                                'Github token needs to be given as argument '
                                'or set in either GITHUB_TOKEN or GITHUB_API_TOKEN '
                                'environment variables')
        try:
            self.initialized = True
            self.headers = {"Authorization": f"token {token}"}
            response = self('{viewer {login}}')
        except Exception:
            self.headers = None
            self.initialized = False
            raise

        try:
            user = response['data']['viewer']['login']
            _logger.debug(f'Github interface initialized (user={user})')
        except Exception:
            _logger.info(f'Github interface initialized ({response})')
        self.headers = {"Authorization": f"token {token}"}

    @staticmethod
    def check(response):
        if not response.ok:
            raise GithubException(f'Error: {response.reason} ({response.status_code})')

    def __call__(self, query, headers=(), **kwargs):
        """
        Call the API (encapsulates a requests call, including headers and error checking).

        :param query: str
            GraphQL query
        :param headers: dict
        :param kwargs: dict
        :return:
        """
        if not self.initialized:
            raise Exception('GithubAPI authentication credentials are not initialized')

        _headers = self.headers.copy()
        _headers.update(headers)
        response = requests.request('post', self.api_url, headers=_headers, json={'query': query},
                                    **kwargs)

        if not response.ok:
            raise GithubException(f'Error: {response.reason} ({response.status_code})')

        return response.json()


GITHUB_API = GithubAPI()
"""THE API"""

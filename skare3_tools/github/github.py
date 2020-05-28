"""
This is a thin wrapper for `Github's REST API`_. It is intended to be easy to extend.
It does not impose much structure on top of what is shown in their online documentation,
and it should be easy to see the correspondence between both.

.. _`Github's REST API`: https://developer.github.com/v3/

Example Usage
^^^^^^^^^^^^^^

.. code-block:: python

      >>> from skare3_tools import github
      >>> github.init(token='c7hvg6pqi3fhqwv0wvlgp4mk9agwbqk1gxc331iz')
      Password:
      >>> repo = github.Repository('sot/Chandra.Maneuver')
      >>> releases = repo.releases()
      >>> for release in releases:
      ...     print(release['name'])
      Release 3.7.2
      Release 3.7.1 with one test fix for 32 bit platform compat.
      Version 3.7
      Version 0.6
      Version 0.05
      >>> prs = repo.pull_requests.create(title='Make namespace package native',
      ...                                 head='namespace',
      ...                                 base='master',
      ...                                 body='The description goes here')
      >>> prs = repo.pull_requests()
      >>> for pr in prs:
      ...     print(f"PR #{pr['number']}: {pr['title']}")
      PR #1: Make namespace package native

It is also possible to use the API directly, in case there is no appropriate high-level method:

.. code-block:: python

      >>> from skare3_tools import github
      >>> api = github.init(token='c7hvg6pqi3fhqwv0wvlgp4mk9agwbqk1gxc331iz')
      >>> last_tag = api.get('/repos/sot/Chandra.Maneuver/releases/latest').json()
      >>> last_tag['tag_name']
      '3.7.2'
"""

import logging
import getpass
import os
import requests
import urllib
try:
    import keyring
except ModuleNotFoundError:
    keyring = None

from requests.auth import HTTPBasicAuth


class AuthException(Exception):
    pass


class RestException(Exception):
    pass


_logger = logging.getLogger('github')
GITHUB_API = None


def init(user=None, password=None, token=None, force=True):
    """
    Initialize the Github API.

    If not token is provided, it tries the following:
    - look for GITHUB_API_TOKEN environmental variable
    - look for GITHUB_TOKEN environmental variable

    If that fails, try with user/password (deprecated)
    If no user name is provided, it tries the following:

    - look for GITHUB_USER environmental variable
    - request in a command line prompt.

    If no password is provided, it tries the following:

    - look for GITHUB_PASSWORD environmental variable
    - try getting it from the keyring (Keychain in Mac OS)

    If user name or password can not be determined, an AuthException is raised.

    :param user: str (deprecated)
    :param password: str (deprecated)
    :param token: str
    :param force: bool
    :return: GithubAPI
    """
    global GITHUB_API
    if GITHUB_API is None or force:
        if token is not None:
            api = GithubAPI(token=os.path.expandvars(token))
        elif 'GITHUB_API_TOKEN' in os.environ:
            api = GithubAPI(token=os.environ['GITHUB_API_TOKEN'])
        elif 'GITHUB_TOKEN' in os.environ:
            api = GithubAPI(token=os.environ['GITHUB_TOKEN'])
        else:
            _logger.warning('Using basic auth, which is deprecated')
            if user is None:
                if 'GITHUB_USER' in os.environ:
                    _logger.debug('Github user from environment')
                    user = os.environ['GITHUB_USER']
                else:
                    _logger.debug('Github user from prompt')
                    user = input('Username: ')
            else:
                _logger.debug('Github user from arguments')
            if password is None:
                if 'GITHUB_PASSWORD' in os.environ:
                    password = os.environ['GITHUB_PASSWORD']
                    _logger.debug('Github password from environment')
                elif keyring:
                    password = keyring.get_password("skare3-github", user)
                    _logger.debug('Github user from keyring')
                if password is None:
                    password = getpass.getpass()
                    _logger.debug('Github user from prompt')
            api = GithubAPI(user=user, password=password)
        r = api.get('')
        if r.status_code == 401:
            raise AuthException(r.json()['message'])
        GITHUB_API = api
        r = GITHUB_API('/user')
        user = r.json()['login']
        _logger.debug(f'Github interface initialized (user={user})')
    return GITHUB_API


class GithubAPI:
    """
    Main class that encapsulates Github's REST API.
    """
    def __init__(self, user=None, password=None, token=None):
        if token is not None:
            self.auth = None
            self.headers = {"Authorization": f"token {token}"}
        else:
            self.auth = HTTPBasicAuth(user, password)
            self.headers = {"Accept": "application/json"}
        self.api_url = 'https://api.github.com'

    @staticmethod
    def check(response):
        if not response.ok:
            raise RestException(f'Error: {response.reason} ({response.status_code})')

    def __call__(self, path, method='get', params=None,
                 check=False, return_json=False, headers=(), **kwargs):
        path = urllib.parse.urlparse(path).path  # make sure it is just the path
        if ':' in path:
            path = '/'.join([f'{{{p[1:]}}}' if p and p[0] == ':' else p for p in path.split('/')])
            path = path.format(**kwargs)
        if path and path[0] == '/':
            path = path[1:]
        url = f'{self.api_url}/{path}'
        _headers = self.headers.copy()
        _headers.update(headers)
        kwargs = {k: v for k, v in kwargs.items() if k in ['json']}
        _logger.debug('%s %s\n  headers: %s\n  params: %s,\n kwargs: %s',
                      url, method, _headers, params, kwargs)
        r = requests.request(method, url, headers=_headers, auth=self.auth, params=params, **kwargs)
        if check:
            self.check(r)
        if return_json:
            if r.content:
                result = r.json()
            else:
                result = {}
            if hasattr(result, 'keys'):
                result['response'] = {
                    'status_code': r.status_code,
                    'ok': r.ok,
                    'reason': r.reason,
                    'message': result['message'] if 'message' in result else ''
                }
            return result
        return r

    def get(self, path, params=None, **kwargs):
        """
        Perform http request using GET method.
        """
        r = self(path, method='get', params=params, **kwargs)
        return r

    def post(self, path, params=None, **kwargs):
        """
        Perform http request using POST method
        """
        r = self(path, method='post', json=params, **kwargs)
        return r

    def put(self, path, params=None, **kwargs):
        """
        Perform http request using PUT method
        """
        r = self(path, method='put', json=params, **kwargs)
        return r

    def patch(self, path, params=None, **kwargs):
        """
        Perform http request using PATCH method
        """
        r = self(path, method='patch', json=params, **kwargs)
        return r


class _EndpointGroup:
    """
    Base class for grouping related endpoints.

    Related endpoints share some arguments.
    """
    def __init__(self, parent, **kwargs):
        self.api = parent.api
        self.args = parent.args.copy()
        self.args.update(kwargs)

    def _method_(self, method, url, **kwargs):
        kwargs.update(self.args)
        url = url.format(**kwargs)
        return self.api(url, method=method, return_json=True, **kwargs)

    def _get(self, url, **kwargs):
        return self._method_('get', url, **kwargs)

    def _put(self, url, **kwargs):
        return self._method_('put', url, **kwargs)

    def _post(self, url, **kwargs):
        return self._method_('post', url, **kwargs)

    def _patch(self, url, **kwargs):
        return self._method_('patch', url, **kwargs)

    def _delete(self, url, **kwargs):
        return self._method_('delete', url, **kwargs)

    def _get_list_generator(self, url, limit=None, **kwargs):
        """
        Generator over items returned via a paginated endpoint.

        Github's API paginates the results when requests return multiple items.
        This method steps through the pages, returning items one by one.

        :param url:
        :param limit:
        :param kwargs:
        :return:
        """
        if 'params' not in kwargs:
            kwargs['params'] = {}
        page = 1
        count = 0
        while True:
            kwargs['params']['page'] = page
            r = self._get(url, **kwargs)
            if type(r) is not list:
                _logger.warning('_get_list_generator received a %s: %s', type(r), r)
                break
            if len(r) == 0:
                break
            _logger.debug('_get_list_generator in page %s, %s entries', page, len(r))
            page += 1
            for item in r:
                yield item
                count += 1
                if limit and count >= limit:
                    raise StopIteration()

    def _get_list(self, *args, **kwargs):
        """
        Generator over items returned via a paginated endpoint.

        Github's API paginates the results when requests return multiple items.
        This method steps through the pages, returning a list of all items.

        :param args:
        :param kwargs:
        :return:
        """
        return [entry for entry in self._get_list_generator(*args, **kwargs)]


class Repository:
    """
    Switchboard for all repository-related endpoints.

    Attributes:
        - releases
        - tags
        - commits
        - issues
        - branches
        - checks
    """
    def __init__(self, repo=None, owner=None, api=None):
        global GITHUB_API
        init()
        self.api = GITHUB_API if api is None else api
        if '/' in repo:
            owner, repo = repo.split('/')
        self.args = {
            'owner': owner,
            'repo': repo
        }

        self.releases = Releases(self)
        self.tags = Tags(self)
        self.commits = Commits(self)
        self.issues = Issues(self)
        self.branches = Branches(self)
        self.checks = Checks(self)
        self.pull_requests = PullRequests(self)
        self.merge = Merge(self)
        self.dispatch_event = DispatchEvent(self)


class Releases(_EndpointGroup):
    """
    Endpoints that have to do with repository releases
    (`releases API docs <https://developer.github.com/v3/repos/releases>`_)
    """
    def __call__(self, latest=False, tag_name=None, release_id=None):
        """

        :param latest:
        :param tag_name:
        :param release_id:
        :return:
        """
        if sum([latest, bool(tag_name), bool(release_id)]) > 1:
            raise Exception('only one of latest, tag_name, release_id can be specified')
        if release_id:
            return self._get('repos/:owner/:repo/releases/:release_id',
                             release_id=release_id)
        elif latest:
            return self._get('repos/:owner/:repo/releases/latest')
        elif tag_name:
            return self._get('repos/:owner/:repo/releases/tags/:tag_name',
                             tag_name=tag_name)
        else:
            return self._get_list('repos/:owner/:repo/releases')

    def create(self, **kwargs):
        """
        :param tag_name: str. Required. The name of the tag.
        :param target_commitish: str.
            Specifies the commitish value that determines where the Git tag is created from.
            Can be any branch or commit SHA. Unused if the Git tag already exists.
            Default: the repository's default branch (usually master).
        :param name: str.
            The name of the release.
        :param body: str.
            Text describing the contents of the tag.
        :param draft: boolean.
            True to create a draft (unpublished) release, false to create a published one.
            Default: false
        :param prerelease: boolean.
            True to identify the release as a prerelease.
            false to identify the release as a full release.
            Default: false
        """
        required = ['tag_name']
        optional = ['target_commitish', 'name', 'body', 'draft', 'prerelease']
        json = {k: kwargs[k] for k in required}
        json.update({k: kwargs[k]for k in optional if k in kwargs})
        kwargs = {k: v for k, v in kwargs.items() if k not in json}
        return self._post('repos/:owner/:repo/releases', json=json, **kwargs)

    def edit(self, release_id, **kwargs):
        """
        :param release_id: str
        :param tag_name: str
            The name of the tag.
        :param target_commitish: str
            Specifies the commitish value that determines where the Git tag is created from.
            Can be any branch or commit SHA. Unused if the Git tag already exists.
            Default: the repository's default branch (usually master).
        :param name: str
            The name of the release.
        :param body: str
            Text describing the contents of the tag.
        :param draft: boolean
            true makes the release a draft, and false publishes the release.
        :param prerelease: boolean
            true to identify the release as a prerelease,
            false to identify the release as a full release.
        """
        required = []
        optional = ['target_commitish', 'name', 'body', 'draft', 'prerelease']
        json = {k: kwargs[k] for k in required}
        json.update({k: kwargs[k]for k in optional if k in kwargs})
        kwargs = {k: v for k, v in kwargs.items() if k not in json}
        return self._patch('repos/:owner/:repo/releases/:release_id',
                           release_id=release_id,
                           json=json,
                           **kwargs)

    def delete(self, release_id):
        return self._delete('repos/:owner/:repo/releases/:release_id', release_id=release_id)


class Tags(_EndpointGroup):
    """
    Endpoints that have to do with repository tags
    (`tags API docs <https://developer.github.com/v3/git/tags>`_)
    """
    def __call__(self, tag_sha=None, name=None):
        if sum([bool(tag_sha), bool(name)]) > 1:
            raise Exception('only one of tag_sha, name can be specified')
        if tag_sha:
            return self._get('repos/:owner/:repo/git/tags/:tag_sha',
                             tag_sha=tag_sha)
        elif name:
            return self._get('repos/:owner/:repo/git/ref/tags/:name',
                             name=name)
        else:
            return self._get_list('repos/:owner/:repo/tags')

    def create(self, **kwargs):
        """
        :param tag: str. Required.
            The tag's name. This is typically a version (e.g., "v0.0.1").
        :param message: str. Required.
            The tag message.
        :param object: str. Required.
            The SHA of the git object this is tagging.
        :param type: str. Required.
            The type of the object we're tagging. Normally this is a commit
            but it can also be a tree or a blob.
        :param tagger: object
            An object with information about the individual creating the tag.

        The tagger object contains the following keys:

        - name: str. The name of the author of the tag
        - email: str. The email of the author of the tag
        - date: str. When this object was tagged.
          This is a timestamp in ISO 8601 format: YYYY-MM-DDTHH:MM:SSZ.
        """
        required = ['tag', 'message', 'object', 'type']
        optional = ['tagger']
        json = {k: kwargs[k] for k in required}
        json.update({k: kwargs[k] for k in optional if k in kwargs})
        kwargs = {k: v for k, v in kwargs.items() if k not in json}
        return self._post('repos/:owner/:repo/git/tags', json=json, **kwargs)


class Commits(_EndpointGroup):
    """
    Endpoints that have to do with repository commits
    (`commit API docs <https://developer.github.com/v3/repos/commits>`_)
    """
    def __call__(self, ref=None, **kwargs):
        """
        :param ref: str
        :param sha: str
            SHA or branch to start listing commits from.
            Default: the repository’s default branch (usually master).
        :param path: str
            Only commits containing this file path will be returned.
        :param author: str
            GitHub login or email address by which to filter by commit author.
        :param since: str
            Only commits after this date will be returned.
            This is a timestamp in ISO 8601 format: YYYY-MM-DDTHH:MM:SSZ.
        :param until: str
            Only commits before this date will be returned.
            This is a timestamp in ISO 8601 format: YYYY-MM-DDTHH:MM:SSZ.

        :param kwargs:
        :return:
        """
        required = []
        optional = ['sha', 'path', 'author', 'since', 'until']
        json = {k: kwargs[k] for k in required}
        json.update({k: kwargs[k] for k in optional if k in kwargs})
        kwargs = {k: v for k, v in kwargs.items() if k not in json}
        if ref is not None:
            return self._get('repos/:owner/:repo/commits/:ref', ref=ref, params=json, **kwargs)
        return self._get_list('repos/:owner/:repo/commits', params=json, **kwargs)


class Branches(_EndpointGroup):
    """
    Endpoints that have to do with repository branches
    (`branches API docs <https://developer.github.com/v3/repos/branches>`_)
    """
    def __call__(self, branch=None, **kwargs):
        """
        :param branch:
        :param protected: bool
            Setting to true returns only protected branches.
            When set to false, only unprotected branches are returned.
            Omitting this parameter returns all branches.
        :param kwargs:
        :return:
        """
        required = []
        optional = ['protected']
        json = {k: kwargs[k] for k in required}
        json.update({k: kwargs[k] for k in optional if k in kwargs})
        kwargs = {k: v for k, v in kwargs.items() if k not in json}
        if branch:
            return self._get('/repos/:owner/:repo/branches/:branch',
                             branch=branch, params=json, **kwargs)
        return self._get_list('repos/:owner/:repo/branches', params=json, **kwargs)


class Issues(_EndpointGroup):
    """
    Endpoints that have to do with repository issues
    (`issues API docs <https://developer.github.com/v3/issues>`_)
    """
    def __call__(self, issue_number=None, **kwargs):
        """
        List issues.

        :param issue_number: int, Optional
        :param filter: str
            Indicates which sorts of issues to return. Default: assigned. Can be one of:

            - assigned: Issues assigned to you
            - created: Issues created by you
            - mentioned: Issues mentioning you
            - subscribed: Issues you're subscribed to updates for
            - all: All issues the authenticated user can see

        :param state: str
            Indicates the state of the issues to return. Can be either open, closed, or all.
            Default: open
        :param labels: str
            A list of comma separated label names. Example: bug,ui,@high
        :param sort: str
            What to sort results by. Can be either created, updated, comments.
            Default: created
        :param direction: str
            The direction of the sort. Can be either asc or desc.
            Default: desc
        :param since: str
            Only issues updated at or after this time are returned.
            This is a timestamp in ISO 8601 format: YYYY-MM-DDTHH:MM:SSZ.
        :param kwargs:
        :return:
        """
        required = []
        optional = ['filter', 'labels', 'sort', 'direction', 'since']
        json = {k: kwargs[k] for k in required}
        json.update({k: kwargs[k] for k in optional if k in kwargs})
        kwargs = {k: v for k, v in kwargs.items() if k not in json}
        if issue_number is not None:
            return self._get('/repos/:owner/:repo/issues/:issue_number',
                             issue_number=issue_number,
                             params=json,
                             **kwargs)
        return self._get_list('repos/:owner/:repo/issues', params=json, **kwargs)

    def create(self, **kwargs):
        """
        :param title: str Required. The title of the issue.
        :param body: str The contents of the issue.
        :param milestone: int
            The number of the milestone to associate this issue with.
            NOTE: Only users with push access can set the milestone for new issues.
            The milestone is silently dropped otherwise.
        :param labels: list
            Labels to associate with this issue.
            NOTE: Only users with push access can set labels for new issues.
            Labels are silently dropped otherwise.
        :param assignees: list
            Logins for Users to assign to this issue.
            NOTE: Only users with push access can set assignees for new issues.
            Assignees are silently dropped otherwise.
        """
        required = ['title']
        optional = ['body', 'milestone', 'labels', 'assignees']
        json = {k: kwargs[k] for k in required}
        json.update({k: kwargs[k] for k in optional if k in kwargs})
        kwargs = {k: v for k, v in kwargs.items() if k not in json}
        return self._post('repos/:owner/:repo/issues', json=json, **kwargs)

    def edit(self, issue_number, **kwargs):
        """
        :param issue_number:
        :param title: str
            The title of the issue.
        :param body: str
            The contents of the issue.
        :param assignee: str
            Login for the user that this issue should be assigned to. This field is deprecated.
        :param state: str
            State of the issue. Either open or closed.
        :param milestone: int
            The number of the milestone to associate this issue with or null to remove current.
            NOTE: Only users with push access can set the milestone for issues.
            The milestone is silently dropped otherwise.
        :param labels: list of strings
            Labels to associate with this issue.
            Pass one or more Labels to replace the set of Labels on this Issue.
            Send an empty array ([]) to clear all Labels from the Issue.
            NOTE: Only users with push access can set labels for issues.
            Labels are silently dropped otherwise.
        :param assignees: list of strings
            Logins for Users to assign to this issue.
            Pass one or more user logins to replace the set of assignees on this Issue.
            Send an empty array ([]) to clear all assignees from the Issue.
            NOTE: Only users with push access can set assignees for new issues.
            Assignees are silently dropped otherwise.
        :param kwargs:
        :return:
        """
        required = []
        optional = ['title', 'body', 'assignee', 'state', 'milestone', 'labels', 'assignees']
        json = {k: kwargs[k] for k in required}
        json.update({k: kwargs[k]for k in optional if k in kwargs})
        kwargs = {k: v for k, v in kwargs.items() if k not in json}
        return self._patch('/repos/:owner/:repo/issues/:issue_number',
                           issue_number=issue_number,
                           json=json,
                           **kwargs)


class PullRequests(_EndpointGroup):
    """
    Endpoints that have to do with pull requests
    (`pull requests API docs <https://developer.github.com/v3/pulls>`_)
    """
    def __call__(self, pull_number=None, **kwargs):
        """
        :param pull_number: str (optional)
            Default: all pulls
        :param state: str
            Either open, closed, or all to filter by state.
            Default: open
        :param head: str
            Filter pulls by head user or head organization and branch name in the format of
            user:ref-name or organization:ref-name. For example:
            github:new-script-format or octocat:test-branch.
        :param base: str
            Filter pulls by base branch name. Example: gh-pages.
        :param sort: str
            What to sort results by. Can be either created, updated, popularity (comment count)
            or long-running (age, filtering by pulls updated in the last month).
            Default: created
        :param direction: str
            The direction of the sort. Can be either asc or desc.
            Default: desc when sort is created or sort is not specified, otherwise asc.
        """
        if pull_number is not None:
            r = self._get('/repos/:owner/:repo/pulls/:pull_number',
                          pull_number=pull_number, **kwargs)
            if r['response']['ok']:
                if 'state' in kwargs and r['state'] != kwargs['state']:
                    return []
                for k in ['head', 'base']:
                    if k in kwargs and r[k]['ref'] != kwargs[k]:
                        return []
                r = [r]
            return r
        if 'head' in kwargs and ':' not in kwargs['head']:
            return {
                "response": {
                    'status_code': 404,
                    'ok': False,
                    'reason':  'head must be in the format user:ref-name or organization:ref-name.'
                }
            }

        required = []
        optional = ['state', 'head', 'base', 'sort', 'direction']
        json = {k: kwargs[k] for k in required}
        json.update({k: kwargs[k]for k in optional if k in kwargs})
        kwargs = {k: v for k, v in kwargs.items() if k not in json}
        return self._get('/repos/:owner/:repo/pulls', params=json, **kwargs)

    def create(self, **kwargs):
        """
        :param title: str Required.
            The title of the new pull request.
        :param head: str Required.
            The name of the branch where your changes are implemented.
            For cross-repository pull requests in the same network,
            namespace head with a user like this: username:branch.
        :param base: str Required.
            The name of the branch you want the changes pulled into.
            This should be an existing branch on the current repository.
            You cannot submit a pull request to one repository that requests
            a merge to a base of another repository.
        :param body: str
            The contents of the pull request.
        :param maintainer_can_modify: bool
            Indicates whether maintainers can modify the pull request.
        :param draft: bool
            Indicates whether the pull request is a draft.
            See "Draft Pull Requests" in the GitHub Help documentation to learn more.
        :param kwargs:
        :return:
        """
        required = ['title', 'head', 'base']
        optional = ['body', 'maintainer_can_modify', 'draft']
        json = {k: kwargs[k] for k in required}
        json.update({k: kwargs[k]for k in optional if k in kwargs})
        kwargs = {k: v for k, v in kwargs.items() if k not in json}
        return self._post('/repos/:owner/:repo/pulls', json=json, **kwargs)

    def edit(self, pull_number, **kwargs):
        """
        :param pull_number:
        :param title: str
            The title of the pull request.
        :param body: str
            The contents of the pull request.
        :param state: str
            State of this Pull Request. Either open or closed.
        :param base: str
            The name of the branch you want your changes pulled into.
            This should be an existing branch on the current repository.
            You cannot update the base branch on a pull request to point to another repository.
        :param maintainer_can_modify: bool
            Indicates whether maintainers can modify the pull request.
        """
        required = []
        optional = ['title', 'body', 'state', 'base', 'maintainer_can_modify']
        json = {k: kwargs[k] for k in required}
        json.update({k: kwargs[k]for k in optional if k in kwargs})
        kwargs = {k: v for k, v in kwargs.items() if k not in json}
        return self._patch('/repos/:owner/:repo/pulls/:pull_number',
                           pull_number=pull_number,
                           json=json,
                           **kwargs)


    def commits(self, pull_number, **kwargs):
        """
        Lists a maximum of 250 commits for a pull request.

        :param pull_number: str
        """
        #  To receive a complete commit list
        #  for pull requests with more than 250 commits, we need to use the Commit List API.
        return self._get('/repos/:owner/:repo/pulls/:pull_number/commits',
                         pull_number=pull_number,
                         **kwargs)

    def files(self, pull_number, **kwargs):
        """
        Lists a maximum of 250 commits for a pull request.

        :param pull_number: str
        """
        #  To receive a complete commit list
        #  for pull requests with more than 250 commits, we need to use the Commit List API.
        return self._get('/repos/:owner/:repo/pulls/:pull_number/files',
                         pull_number=pull_number,
                         **kwargs)


    def status(self, pull_number, **kwargs):
        """
        Get if a pull request has been merged

        :param pull_number: str
        """
        #  To receive a complete commit list
        #  for pull requests with more than 250 commits, we need to use the Commit List API.
        return self._get('/repos/:owner/:repo/pulls/:pull_number/merge',
                         pull_number=pull_number,
                         **kwargs)


    def merge(self, pull_number, **kwargs):
        """
        Merge a pull request

        :param pull_number:
        :param commit_title: str
            Title for the automatic commit message.
        :param commit_message: str
            Extra detail to append to automatic commit message.
        :param sha: str
            SHA that pull request head must match to allow merge.
        :param merge_method: str
            Merge method to use. Possible values are merge, squash or rebase. Default is merge.
        """
        required = ['commit_title', 'commit_message', 'sha']
        optional = ['merge_method']
        json = {k: kwargs[k] for k in required}
        json.update({k: kwargs[k]for k in optional if k in kwargs})
        kwargs = {k: v for k, v in kwargs.items() if k not in json}
        return self._put('/repos/:owner/:repo/pulls/:pull_number/merge',
                         pull_number=pull_number,
                         params=json, **kwargs)


class Merge(_EndpointGroup):
    """
    Single endpoint for merges
    (`merges API docs <https://developer.github.com/v3/repos/merging/>`_)

    Note: this is for branches. Merging pull requests is done with the pull requests API
    """
    def __call__(self, **kwargs):
        """
        Merge a branch

        :param base: str
            The name of the base branch that the head will be merged into.
        :param head: str
            The head to merge. This can be a branch name or a commit SHA1.
        :param commit_message: str. optional
            Commit message to use for the merge commit. If omitted, a default message will be used.
        """
        required = ['base', 'head']
        optional = ['commit_message']
        json = {k: kwargs[k] for k in required}
        json.update({k: kwargs[k]for k in optional if k in kwargs})
        kwargs = {k: v for k, v in kwargs.items() if k not in json}
        return self._post('/repos/:owner/:repo/pulls/:pull_number/merge', params=json, **kwargs)


class Checks(_EndpointGroup):
    """
    Endpoints that have to do with repository checks
    (`checks API docs <https://developer.github.com/v3/checks>`_)
    """
    def __call__(self, ref):
        # accept headers are custom because this endpoint is
        # on preview for developers and can change any time
        return self._get('repos/:owner/:repo/commits/:ref/check-runs',
                         headers={'Accept': 'application/vnd.github.antiope-preview+json'},
                         ref=ref)

class DispatchEvent(_EndpointGroup):
    def __call__(self, event_type, client_payload={}):
        params = {'event_type': event_type,
                  'client_payload': client_payload}
        return self._post('/repos/:owner/:repo/dispatches',
                          json=params)


class Repositories(_EndpointGroup):
    def __call__(self):
        return self._get_list('orgs/:owner/repos')


class Organization:
    def __init__(self, name):
        self.api = GITHUB_API
        self.args = {'owner': name}

        self.repositories = Repositories(self)

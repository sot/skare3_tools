"""
This is a thin wrapper for `Github's REST API`_ (V3). It is intended to be easy to extend.
It does not impose much structure on top of what is shown in their online documentation,
and it should be easy to see the correspondence between both.

.. _`Github's REST API`: https://developer.github.com/v3/

As an example, this is how one gets a list of releases and pull requests for a repository:

.. code-block:: python

      >>> from skare3_tools import github
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
      >>> last_tag = github.GITHUB_API_V3.get('/repos/sot/Chandra.Maneuver/releases/latest').json()
      >>> last_tag['tag_name']
      '3.7.2'

Getting and Editing Content
^^^^^^^^^^^^^^^^^^^^^^^^^^^

Getting content:

    >>> from skare3_tools.github import github
    >>> r = github.Repository('sot/test-actions')
    >>> c = r.contents('README.md')
    >>> c['content']
    '# test-actions\\n\\nA realistic package with which to test GitHub actions...'

Editing content:

    >>> from skare3_tools.github import github
    >>> r = github.Repository('sot/test-actions')
    >>> content = \"""
    ... # test-actions
    ...
    ... A realistic package with which to test GitHub actions and play around.
    ... \"""
    >>> r.contents.edit('README.md', message='changing readme', content=content)

Repository Dispatch
^^^^^^^^^^^^^^^^^^^

A typical use is to dispatch an event to cause an action. For example, the docs for some
repositories are deployed when a repository_dispatch event of type 'build-docs' is triggered.
This can be seen in the corresponding workflow::

    name: Deploy Docs
    on:
      repository_dispatch:
        types:
        - build-docs

In this case, one can do::

    >>> from skare3_tools import github
    >>> r = github.Repository('sot/skare3_tools')  # changing the repository name accordingly!
    >>> r.dispatch_event(event_type='build-docs')

"""

import logging
import os
import urllib

import requests

try:
    import keyring
except ModuleNotFoundError:
    keyring = None

from requests.auth import HTTPBasicAuth


class AuthException(Exception):
    pass


class RestException(Exception):
    pass


_logger = logging.getLogger("github")


def init(user=None, password=None, token=None, force=True):
    """
    Initialize the API.

    :param token: str
        a Github auth token
    :param force: bool
        override a previously initialized API
    :return:
    """
    GITHUB_API.init(user, password, token, force)
    return GITHUB_API


def _get_user_password(user, password):
    if user is None:
        if "GITHUB_USER" in os.environ:
            _logger.debug("Github user from environment")
            user = os.environ["GITHUB_USER"]
    else:
        _logger.debug("Github user from arguments")
    if password is None:
        if "GITHUB_PASSWORD" in os.environ:
            password = os.environ["GITHUB_PASSWORD"]
            _logger.debug("Github password from environment")
        elif keyring:
            try:
                password = keyring.get_password("skare3-github", user)
                _logger.debug("Github user from keyring")
            except RuntimeError as e:
                import re

                if re.match("No recommended backend was available", str(e)):
                    _logger.debug("keyring backend failed")
    return user, password


class GithubAPI:
    """
    Main class that encapsulates Github's REST API.
    """

    def __init__(self, user=None, password=None, token=None):
        self.initialized = False
        self.auth = None
        self.headers = None
        self.api_url = "https://api.github.com"

        try:
            self.init(user, password, token)
        except AuthException:
            # the exception is not raised if we are creating the API with default args.
            # An exception will be raised later, when one tries to use it.
            if not (user is None and password is None and token is None):
                raise

    def __bool__(self):
        return self.initialized

    def init(self, user=None, password=None, token=None, force=True):
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
        if self.initialized and not force:
            return

        if token is None:
            if "GITHUB_API_TOKEN" in os.environ:
                token = os.environ["GITHUB_API_TOKEN"]
            elif "GITHUB_TOKEN" in os.environ:
                token = os.environ["GITHUB_TOKEN"]

        if token is not None:
            self.auth = None
            self.headers = {"Authorization": f"token {token}"}
        else:
            user, password = _get_user_password(user, password)
            if user and password:
                _logger.warning("Using basic auth, which is deprecated")
            self.auth = HTTPBasicAuth(user, password)
            self.headers = {"Accept": "application/json"}

        try:
            self.initialized = True
            r = self.get("")
            if r.status_code == 401:
                msg = r.json()["message"] + ". "
                msg += (
                    "Github token should be given as argument "
                    "or set in either GITHUB_TOKEN or GITHUB_API_TOKEN "
                    "environment variables"
                )
                raise AuthException(msg)
            if not r.ok:
                msg = r.json()["message"]
                raise AuthException(msg)

            r = self("/user").json()
            if "login" in r:
                user = r["login"]
                _logger.debug(f"Github interface initialized (user={user})")
            else:
                _logger.info(f"Github interface initialized: {r}")
        except Exception:
            self.auth = None
            self.headers = None
            self.initialized = False
            raise

    @staticmethod
    def check(response):
        if not response.ok:
            raise RestException(f"Error: {response.reason} ({response.status_code})")

    def __call__(
        self,
        endpoint_str,
        method="get",
        params=None,
        check=False,
        return_json=False,
        headers=(),
        **kwargs,
    ):
        if not self.initialized:
            raise Exception("GithubAPI authentication credentials are not initialized")

        endpoint_str = urllib.parse.urlparse(
            endpoint_str
        ).path  # make sure it is just the path
        if ":" in endpoint_str:
            endpoint_str = "/".join(
                [
                    f"{{{p[1:]}}}" if p and p[0] == ":" else p
                    for p in endpoint_str.split("/")
                ]
            )
            endpoint_str = endpoint_str.format(**kwargs)
        if endpoint_str and endpoint_str[0] == "/":
            endpoint_str = endpoint_str[1:]
        url = f"{self.api_url}/{endpoint_str}"
        _headers = self.headers.copy()
        _headers.update(headers)
        kwargs = {k: v for k, v in kwargs.items() if k in ["json"]}
        _logger.debug(
            "%s %s\n  headers: %s\n  params: %s,\n kwargs: %s",
            url,
            method,
            _headers,
            params,
            kwargs,
        )
        r = requests.request(
            method, url, headers=_headers, auth=self.auth, params=params, **kwargs
        )
        if check:
            self.check(r)
        if return_json:
            if r.content:
                result = r.json()
            else:
                result = {}
            if hasattr(result, "keys"):
                result["response"] = {
                    "status_code": r.status_code,
                    "ok": r.ok,
                    "reason": r.reason,
                    "message": result["message"] if "message" in result else "",
                }
            return result
        return r

    def get(self, path, params=None, **kwargs):
        """
        Perform http request using GET method.
        """
        r = self(path, method="get", params=params, **kwargs)
        return r

    def post(self, path, params=None, **kwargs):
        """
        Perform http request using POST method
        """
        r = self(path, method="post", json=params, **kwargs)
        return r

    def put(self, path, params=None, **kwargs):
        """
        Perform http request using PUT method
        """
        r = self(path, method="put", json=params, **kwargs)
        return r

    def patch(self, path, params=None, **kwargs):
        """
        Perform http request using PATCH method
        """
        r = self(path, method="patch", json=params, **kwargs)
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
        if "return_json" not in kwargs:
            kwargs["return_json"] = True
        return self.api(url, method=method, **kwargs)

    def _get(self, url, **kwargs):
        return self._method_("get", url, **kwargs)

    def _put(self, url, **kwargs):
        return self._method_("put", url, **kwargs)

    def _post(self, url, **kwargs):
        return self._method_("post", url, **kwargs)

    def _patch(self, url, **kwargs):
        return self._method_("patch", url, **kwargs)

    def _delete(self, url, **kwargs):
        return self._method_("delete", url, **kwargs)

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
        if "params" not in kwargs:
            kwargs["params"] = {}
        page = 1
        count = 0
        while True:
            kwargs["params"]["page"] = page
            r = self._get(url, **kwargs)
            if type(r) is not list:
                _logger.warning("_get_list_generator received a %s: %s", type(r), r)
                break
            if len(r) == 0:
                break
            _logger.debug("_get_list_generator in page %s, %s entries", page, len(r))
            page += 1
            for item in r:
                yield item
                count += 1
                if limit and count >= limit:
                    return

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
        self.api = GITHUB_API if api is None else api
        if "/" in repo:
            owner, repo = repo.split("/")
        self.args = {"owner": owner, "repo": repo}
        self.info = self.api.get("/repos/:owner/:repo", return_json=True, **self.args)

        self.releases = Releases(self)
        self.tags = Tags(self)
        self.commits = Commits(self)
        self.issues = Issues(self)
        self.branches = Branches(self)
        self.checks = Checks(self)
        self.pull_requests = PullRequests(self)
        self.merge = Merge(self)
        self.dispatch_event = DispatchEvent(self)
        self.contents = Contents(self)

        self.workflows = Workflows(self)
        self.runs = Runs(self)
        self.artifacts = Artifacts(self)
        self.jobs = Jobs(self)


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
            raise Exception("only one of latest, tag_name, release_id can be specified")
        if release_id:
            return self._get(
                "repos/:owner/:repo/releases/:release_id", release_id=release_id
            )
        elif latest:
            return self._get("repos/:owner/:repo/releases/latest")
        elif tag_name:
            return self._get(
                "repos/:owner/:repo/releases/tags/:tag_name", tag_name=tag_name
            )
        else:
            return self._get_list("repos/:owner/:repo/releases")

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
        required = ["tag_name"]
        optional = ["target_commitish", "name", "body", "draft", "prerelease"]
        json = {k: kwargs[k] for k in required}
        json.update({k: kwargs[k] for k in optional if k in kwargs})
        kwargs = {k: v for k, v in kwargs.items() if k not in json}
        return self._post("repos/:owner/:repo/releases", json=json, **kwargs)

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
        optional = ["target_commitish", "name", "body", "draft", "prerelease"]
        json = {k: kwargs[k] for k in required}
        json.update({k: kwargs[k] for k in optional if k in kwargs})
        kwargs = {k: v for k, v in kwargs.items() if k not in json}
        return self._patch(
            "repos/:owner/:repo/releases/:release_id",
            release_id=release_id,
            json=json,
            **kwargs,
        )

    def delete(self, release_id):
        return self._delete(
            "repos/:owner/:repo/releases/:release_id", release_id=release_id
        )


class Tags(_EndpointGroup):
    """
    Endpoints that have to do with repository tags
    (`tags API docs <https://developer.github.com/v3/git/tags>`_)
    """

    def __call__(self, tag_sha=None, name=None):
        if sum([bool(tag_sha), bool(name)]) > 1:
            raise Exception("only one of tag_sha, name can be specified")
        if tag_sha:
            return self._get("repos/:owner/:repo/git/tags/:tag_sha", tag_sha=tag_sha)
        elif name:
            return self._get("repos/:owner/:repo/git/ref/tags/:name", name=name)
        else:
            return self._get_list("repos/:owner/:repo/tags")

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
        required = ["tag", "message", "object", "type"]
        optional = ["tagger"]
        json = {k: kwargs[k] for k in required}
        json.update({k: kwargs[k] for k in optional if k in kwargs})
        kwargs = {k: v for k, v in kwargs.items() if k not in json}
        return self._post("repos/:owner/:repo/git/tags", json=json, **kwargs)


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
        optional = ["sha", "path", "author", "since", "until"]
        json = {k: kwargs[k] for k in required}
        json.update({k: kwargs[k] for k in optional if k in kwargs})
        kwargs = {k: v for k, v in kwargs.items() if k not in json}
        if ref is not None:
            return self._get(
                "repos/:owner/:repo/commits/:ref", ref=ref, params=json, **kwargs
            )
        return self._get_list("repos/:owner/:repo/commits", params=json, **kwargs)


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
        optional = ["protected"]
        json = {k: kwargs[k] for k in required}
        json.update({k: kwargs[k] for k in optional if k in kwargs})
        kwargs = {k: v for k, v in kwargs.items() if k not in json}
        if branch:
            return self._get(
                "/repos/:owner/:repo/branches/:branch",
                branch=branch,
                params=json,
                **kwargs,
            )
        return self._get_list("repos/:owner/:repo/branches", params=json, **kwargs)


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
        optional = ["filter", "labels", "sort", "direction", "since"]
        json = {k: kwargs[k] for k in required}
        json.update({k: kwargs[k] for k in optional if k in kwargs})
        kwargs = {k: v for k, v in kwargs.items() if k not in json}
        if issue_number is not None:
            return self._get(
                "/repos/:owner/:repo/issues/:issue_number",
                issue_number=issue_number,
                params=json,
                **kwargs,
            )
        return self._get_list("repos/:owner/:repo/issues", params=json, **kwargs)

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
        required = ["title"]
        optional = ["body", "milestone", "labels", "assignees"]
        json = {k: kwargs[k] for k in required}
        json.update({k: kwargs[k] for k in optional if k in kwargs})
        kwargs = {k: v for k, v in kwargs.items() if k not in json}
        return self._post("repos/:owner/:repo/issues", json=json, **kwargs)

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
        optional = [
            "title",
            "body",
            "assignee",
            "state",
            "milestone",
            "labels",
            "assignees",
        ]
        json = {k: kwargs[k] for k in required}
        json.update({k: kwargs[k] for k in optional if k in kwargs})
        kwargs = {k: v for k, v in kwargs.items() if k not in json}
        return self._patch(
            "/repos/:owner/:repo/issues/:issue_number",
            issue_number=issue_number,
            json=json,
            **kwargs,
        )


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
            r = self._get(
                "/repos/:owner/:repo/pulls/:pull_number",
                pull_number=pull_number,
                **kwargs,
            )
            if r["response"]["ok"]:
                if "state" in kwargs and r["state"] != kwargs["state"]:
                    return []
                for k in ["head", "base"]:
                    if k in kwargs and r[k]["ref"] != kwargs[k]:
                        return []
                r = [r]
            return r
        if "head" in kwargs and ":" not in kwargs["head"]:
            return {
                "response": {
                    "status_code": 404,
                    "ok": False,
                    "reason": "head must be in the format user:ref-name or organization:ref-name.",
                }
            }

        required = []
        optional = ["state", "head", "base", "sort", "direction"]
        json = {k: kwargs[k] for k in required}
        json.update({k: kwargs[k] for k in optional if k in kwargs})
        kwargs = {k: v for k, v in kwargs.items() if k not in json}
        return self._get_list("/repos/:owner/:repo/pulls", params=json, **kwargs)

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
        required = ["title", "head", "base"]
        optional = ["body", "maintainer_can_modify", "draft"]
        json = {k: kwargs[k] for k in required}
        json.update({k: kwargs[k] for k in optional if k in kwargs})
        kwargs = {k: v for k, v in kwargs.items() if k not in json}
        return self._post("/repos/:owner/:repo/pulls", json=json, **kwargs)

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
        optional = ["title", "body", "state", "base", "maintainer_can_modify"]
        json = {k: kwargs[k] for k in required}
        json.update({k: kwargs[k] for k in optional if k in kwargs})
        kwargs = {k: v for k, v in kwargs.items() if k not in json}
        return self._patch(
            "/repos/:owner/:repo/pulls/:pull_number",
            pull_number=pull_number,
            json=json,
            **kwargs,
        )

    def commits(self, pull_number, **kwargs):
        """
        Lists a maximum of 250 commits for a pull request.

        :param pull_number: str
        """
        #  To receive a complete commit list
        #  for pull requests with more than 250 commits, we need to use the Commit List API.
        return self._get(
            "/repos/:owner/:repo/pulls/:pull_number/commits",
            pull_number=pull_number,
            **kwargs,
        )

    def files(self, pull_number, **kwargs):
        """
        Lists a maximum of 250 commits for a pull request.

        :param pull_number: str
        """
        #  To receive a complete commit list
        #  for pull requests with more than 250 commits, we need to use the Commit List API.
        return self._get(
            "/repos/:owner/:repo/pulls/:pull_number/files",
            pull_number=pull_number,
            **kwargs,
        )

    def status(self, pull_number, **kwargs):
        """
        Get if a pull request has been merged

        :param pull_number: str
        """
        #  To receive a complete commit list
        #  for pull requests with more than 250 commits, we need to use the Commit List API.
        return self._get(
            "/repos/:owner/:repo/pulls/:pull_number/merge",
            pull_number=pull_number,
            **kwargs,
        )

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
        required = ["commit_title", "commit_message", "sha"]
        optional = ["merge_method"]
        json = {k: kwargs[k] for k in required}
        json.update({k: kwargs[k] for k in optional if k in kwargs})
        kwargs = {k: v for k, v in kwargs.items() if k not in json}
        return self._put(
            "/repos/:owner/:repo/pulls/:pull_number/merge",
            pull_number=pull_number,
            params=json,
            **kwargs,
        )


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
        required = ["base", "head"]
        optional = ["commit_message"]
        json = {k: kwargs[k] for k in required}
        json.update({k: kwargs[k] for k in optional if k in kwargs})
        kwargs = {k: v for k, v in kwargs.items() if k not in json}
        return self._post(
            "/repos/:owner/:repo/pulls/:pull_number/merge", params=json, **kwargs
        )


class Workflows(_EndpointGroup):
    """
    Endpoints that have to do with workflows
    (`Workflows docs <https://developer.github.com/v3/actions/workflows>`_)
    """

    def __call__(self, workflow_id=None, **kwargs):
        required = []
        optional = []
        json = {k: kwargs[k] for k in required}
        json.update({k: kwargs[k] for k in optional if k in kwargs})
        kwargs = {k: v for k, v in kwargs.items() if k not in json}
        if workflow_id is not None:
            return self._get(
                "repos/:owner/:repo/actions/workflows/:workflow_id",
                workflow_id=workflow_id,
                params=json,
                **kwargs,
            )
        return self._get("repos/:owner/:repo/actions/workflows")


class Artifacts(_EndpointGroup):
    """
    Endpoints that have to do with artifacts
    (`Artifacts docs <https://developer.github.com/v3/actions/artifacts>`_)
    """

    def __call__(self, artifact_id=None, run_id=None, **kwargs):
        required = []
        optional = []
        json = {k: kwargs[k] for k in required}
        json.update({k: kwargs[k] for k in optional if k in kwargs})
        kwargs = {k: v for k, v in kwargs.items() if k not in json}
        if run_id is not None:
            return self._get(
                "/repos/:owner/:repo/actions/runs/:run_id/artifacts",
                run_id=run_id,
                params=json,
                **kwargs,
            )["artifacts"]
        elif artifact_id is not None:
            return self._get(
                "/repos/:owner/:repo/actions/artifacts/:artifact_id",
                artifact_id=artifact_id,
                params=json,
                **kwargs,
            )
        return self._get("/repos/:owner/:repo/actions/artifacts")["artifacts"]

    def download(self, artifact_id, path):
        r = self._get(
            "/repos/:owner/:repo/actions/artifacts/:artifact_id/zip",
            artifact_id=artifact_id,
            return_json=False,
        )
        chunk_size = 128
        with open(path, "wb") as fd:
            for chunk in r.iter_content(chunk_size=chunk_size):
                fd.write(chunk)

    def delete(self, artifact_id):
        return self._delete(
            "/repos/:owner/:repo/actions/artifacts/:artifact_id",
            artifact_id=artifact_id,
        )


class Jobs(_EndpointGroup):
    """
    Endpoints that have to do with workflow jobs
    (`Workflow-jobs docs <https://developer.github.com/v3/actions/workflow-jobs>`_)
    """

    def __call__(self, run_id=None, job_id=None, **kwargs):
        required = []
        optional = []
        json = {k: kwargs[k] for k in required}
        json.update({k: kwargs[k] for k in optional if k in kwargs})
        kwargs = {k: v for k, v in kwargs.items() if k not in json}
        if run_id is not None:
            return self._get(
                "/repos/:owner/:repo/actions/workflows/:run_id/jobs",
                workflow_id=run_id,
                params=json,
                **kwargs,
            )
        return self._get("/repos/:owner/:repo/actions/jobs/:job_id", job_id=job_id)

    def download_logs(self, job_id):
        return self._get("/repos/:owner/:repo/actions/jobs/:job_id/logs", job_id=job_id)


class Runs(_EndpointGroup):
    """
    Endpoints that have to do with workflow runs
    (`Workflow-runs docs <https://developer.github.com/v3/actions/workflow-runs>`_)
    """

    def __call__(self, workflow_id=None, run_id=None, **kwargs):
        """
        :param workflow_id:
        :param run_id:
        :param actor: str
            Returns someone's workflow runs. Use the login for the user who created the
            push associated with the check suite or workflow run.
        :param branch: str
            Returns workflow runs associated with a branch. Use the name of the branch of the push.
        :param event: str
            Returns workflow run triggered by the event you specify.
            For example, push, pull_request or issue. For more information,
            see "Events that trigger workflows" in the GitHub Help documentation.
        :param status: str
            Returns workflow runs associated with the check run status or conclusion you specify.
            For example, a conclusion can be success or a status can be completed.
            For more information, see the status and conclusion options available in
            "Create a check run."
        :return:
        """
        required = []
        optional = ["actor", "branch", "event", "status"]
        json = {k: kwargs[k] for k in required}
        json.update({k: kwargs[k] for k in optional if k in kwargs})
        kwargs = {k: v for k, v in kwargs.items() if k not in json}
        if workflow_id is not None:
            return self._get(
                "/repos/:owner/:repo/actions/workflows/:workflow_id/runs",
                workflow_id=workflow_id,
                params=json,
                **kwargs,
            )["workflow_runs"]
        elif run_id is not None:
            return self._get(
                "/repos/:owner/:repo/actions/runs/:run_id",
                run_id=run_id,
                params=json,
                **kwargs,
            )
        return self._get("repos/:owner/:repo/actions/runs")["workflow_runs"]

    def re_run(self, run_id):
        return self._post(
            "/repos/:owner/:repo/actions/runs/:run_id/rerun", run_id=run_id
        )

    def cancel(self, run_id):
        return self._post(
            "/repos/:owner/:repo/actions/runs/:run_id/cancel", run_id=run_id
        )

    def download_logs(self, run_id):
        return self._get("/repos/:owner/:repo/actions/runs/:run_id/logs", run_id=run_id)

    def delete_logs(self, run_id):
        return self._delete(
            "/repos/:owner/:repo/actions/runs/:run_id/logs", run_id=run_id
        )

    def usage(self, run_id):
        return self._get(
            "/repos/:owner/:repo/actions/runs/:run_id/timing", run_id=run_id
        )


class Checks(_EndpointGroup):
    """
    Endpoints that have to do with repository checks
    (`checks API docs <https://developer.github.com/v3/checks>`_)
    """

    def __call__(self, ref):
        # accept headers are custom because this endpoint is
        # on preview for developers and can change any time
        return self._get(
            "repos/:owner/:repo/commits/:ref/check-runs",
            headers={"Accept": "application/vnd.github.antiope-preview+json"},
            ref=ref,
        )


class DispatchEvent(_EndpointGroup):
    """
    Create a repository dispatch event
    """

    def __call__(self, event_type, client_payload={}):
        """
        Create a repository dispatch event

        :param event_type: str
            A custom webhook event name.
        :param client_payload: dict
            JSON payload with extra information about the webhook event.
        """
        params = {"event_type": event_type, "client_payload": client_payload}
        return self._post("/repos/:owner/:repo/dispatches", json=params)


class Contents(_EndpointGroup):
    """
    Create and edit repository content
    (`contents API docs  <https://developer.github.com/v3/repos/contents/>`_)
    """

    def __call__(self, path="", decode=True, **kwargs):
        """
        Gets the contents of a file or directory in a repository.
        If path is omitted, it returns all the contents of the repository.

        :param path: str
        :param decode: bool
            if True, the contents are base64 decoded.
        :param ref: str
            name of the commit/branch/tag (default: the repository’s default branch (usually master)
        """
        import base64

        required = []
        optional = ["ref"]
        json = {k: kwargs[k] for k in required}
        json.update({k: kwargs[k] for k in optional if k in kwargs})
        kwargs = {k: v for k, v in kwargs.items() if k not in json}
        c = self._get(
            "/repos/:owner/:repo/contents/:path", path=path, params=json, **kwargs
        )
        if decode and "content" in c and c["response"]["ok"]:
            c["content"] = base64.b64decode(c["content"]).decode()
        return c

    def edit(self, path, encode=True, **kwargs):
        """
        Create or update file contents

        :param message:	str	Required.
            The commit message.
        :param content:	str	Required.
            The new file content.
        :param sha:	str
            if you are updating a file. The blob SHA of the file being replaced.
        :param branch:	str
            The branch name. Default: the repository’s default branch (usually master)
        :param committer:	dict
            The person that committed the file. Default: the authenticated user.
        :param author:	dict
            The author of the file. Default: The committer or the authenticated user.
            Both the author and committer parameters have the same keys: {'name': '', 'email': ''}
        :param encode: bool
            if True, the content argument is plain text, this function will encode it.
            default True
        :return:
        """
        import base64

        if "sha" not in kwargs:
            args = {"path": path}
            if "branch" in kwargs:
                args["ref"] = kwargs["branch"]
            c = self(**args)
            if "sha" in c:
                kwargs["sha"] = c["sha"]

        if encode:
            kwargs["content"] = base64.b64encode(kwargs["content"].encode()).decode()

        required = ["message", "content"]
        optional = ["branch", "committer", "author", "sha"]
        json = {k: kwargs[k] for k in required}
        json.update({k: kwargs[k] for k in optional if k in kwargs})
        kwargs = {k: v for k, v in kwargs.items() if k not in json}
        return self._put(
            "/repos/:owner/:repo/contents/:path", path=path, json=json, **kwargs
        )


class Repositories(_EndpointGroup):
    def __call__(self):
        return self._get_list("orgs/:owner/repos")


class Organization:
    def __init__(self, name):
        self.api = GITHUB_API
        self.args = {"owner": name}

        self.repositories = Repositories(self)


GITHUB_API = GithubAPI()

.. SkaRE3 Tools documentation master file, created by
   sphinx-quickstart on Tue Jan 28 14:06:27 2020.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

SkaRE3 Tools
=============

.. toctree::
   :maxdepth: 2
   :caption: Contents:

.. contents::
   :depth: 4


Github API
----------

.. automodule:: skare3_tools.github.github

Github Scripts
^^^^^^^^^^^^^^

skare3-create-issue
"""""""""""""""""""

.. argparse::
   :ref: skare3_tools.github.scripts.create_issue.parser
   :prog: skare3-create-issue

skare3-add-secrets
"""""""""""""""""""

.. argparse::
   :ref: skare3_tools.github.scripts.add_secrets.parser
   :prog: skare3-add-secrets

skare3-create-issue
"""""""""""""""""""

.. argparse::
   :ref: skare3_tools.github.scripts.create_issue.parser
   :prog: skare3-create-issue

skare3-create-pr
"""""""""""""""""""

.. argparse::
   :ref: skare3_tools.github.scripts.create_pr.parser
   :prog: skare3-create-pr

skare3-merge-pr
"""""""""""""""

.. argparse::
   :ref: skare3_tools.github.scripts.merge_pr.parser

skare3-release-merge-info
"""""""""""""""""""""""""

.. argparse::
   :ref: skare3_tools.github.scripts.release_merge_info.parser


Github API Documentation
^^^^^^^^^^^^^^^^^^^^^^^^

.. autofunction:: skare3_tools.github.github.init

.. autoclass:: skare3_tools.github.github.GithubAPI
   :members:

.. autoclass:: skare3_tools.github.github.Repository
   :members:

Repositories Details
""""""""""""""""""""

.. autoclass:: skare3_tools.github.github.Releases
   :members: __call__, create, edit

.. autoclass:: skare3_tools.github.github.Tags
   :members: __call__, create

.. autoclass:: skare3_tools.github.github.Commits
   :members: __call__

.. autoclass:: skare3_tools.github.github.Issues
   :members: __call__, create, edit

.. autoclass:: skare3_tools.github.github.Branches
   :members: __call__

.. autoclass:: skare3_tools.github.github.PullRequests
   :members: __call__, create, edit, merge, status, commits, files

.. autoclass:: skare3_tools.github.github.Checks
   :members: __call__


Packages
--------

.. automodule:: skare3_tools.packages

Packages Scripts
^^^^^^^^^^^^^^^^

skare3-github-info
""""""""""""""""""
.. argparse::
   :ref: skare3_tools.packages.get_parser
   :prog: skare3-github-info

Dashboard
---------

Scripts
^^^^^^^

skare3-dashboard
"""""""""""""""""

.. argparse::
   :ref: skare3_tools.dashboard.views.dashboard.get_parser
   :prog: skare3-dashboard

skare3-test-dashboard
"""""""""""""""""""""

.. argparse::
   :ref: skare3_tools.dashboard.views.test_results.get_parser
   :prog: skare3-test-dashboard

Other Scripts
-------------

skare3-bulk
^^^^^^^^^^^

.. argparse::
   :ref: skare3_tools.scripts.bulk.parser
   :prog: skare3-bulk

skare3-build
^^^^^^^^^^^^

.. argparse::
   :ref: skare3_tools.scripts.build.get_parser
   :prog: skare3-build

skare3-release-check
^^^^^^^^^^^^^^^^^^^^

.. argparse::
   :ref: skare3_tools.scripts.skare3_release_check.parser
   :prog: skare3-release-check

skare3-test-results
^^^^^^^^^^^^^^^^^^^

.. argparse::
   :ref: skare3_tools.test_results.parser
   :prog: skare3-test-results

skare3-changes-summary
^^^^^^^^^^^^^^^^^^^^^^

.. argparse::
   :ref: skare3_tools.scripts.skare3_update_summary.parser
   :prog: skare3-changes-summary

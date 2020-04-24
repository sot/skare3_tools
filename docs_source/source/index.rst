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

skare3-github-info
""""""""""""""""""
.. argparse::
   :ref: skare3_tools.github.scripts.ska_github_info.get_parser
   :prog: skare3-github-info

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

Google Drive
------------

.. automodule:: skare3_tools.gdrive.gdrive

Google Drive Scripts
^^^^^^^^^^^^^^^^^^^^

gdrive
""""""
.. argparse::
   :ref: skare3_tools.gdrive.scripts.gdrive.get_parser
   :prog: gdrive


Google Drive API Documentation
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. autofunction:: skare3_tools.gdrive.gdrive.init

.. autofunction:: skare3_tools.gdrive.gdrive.ls

.. autofunction:: skare3_tools.gdrive.gdrive.walk

.. autofunction:: skare3_tools.gdrive.gdrive.trash

.. autofunction:: skare3_tools.gdrive.gdrive.delete

.. autofunction:: skare3_tools.gdrive.gdrive.download

.. autofunction:: skare3_tools.gdrive.gdrive.upload

.. autofunction:: skare3_tools.gdrive.gdrive.get_ids

.. autofunction:: skare3_tools.gdrive.gdrive.get

.. autofunction:: skare3_tools.gdrive.gdrive.get_drive_id

Dashboard
---------

Scripts
^^^^^^^

skare3-dashboard
"""""""""""""""""

.. argparse::
   :ref: skare3_tools.dashboard.dashboard.get_parser
   :prog: skare3-dashboard

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

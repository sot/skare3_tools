Github
------

.. automodule:: skare3_tools.github

REST Interface (V3)
^^^^^^^^^^^^^^^^^^^

.. automodule:: skare3_tools.github.github

GraphQL Interface (V4)
^^^^^^^^^^^^^^^^^^^^^^

.. automodule:: skare3_tools.github.graphql

Github Scripts
^^^^^^^^^^^^^^

Some of these scripts are superseded by `Github's own CLI`_,
while some provide functionality specific to Ska. At the very least,
the exemplify the usage of the API.

.. _`Github's own CLI`: https://cli.github.com/

skare3-create-issue
"""""""""""""""""""

.. argparse::
   :ref: skare3_tools.github.scripts.create_issue.parser
   :prog: skare3-create-issue

skare3-create-pr
""""""""""""""""

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

skare3-add-secrets
"""""""""""""""""""

.. argparse::
   :ref: skare3_tools.github.scripts.add_secrets.parser
   :prog: skare3-add-secrets
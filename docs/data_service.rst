Data Service
============

Package and test-result data is consolidated in a single on-disk store,
written by exactly one producer and read by everything else.

The store
---------

The store root is in ``$SKA/data/skare3/skare3_data/data`` (configured in skare3_tools via
``CONFIG["data_dir"]``). It holds:

- ``manifest.json`` — schema version, generation time, producer identity, and
  the excluded repositories,
- ``repository_status.json`` — operator-edited input mapping ``owner/repo`` to
  ``"deprecated"`` or ``"ignored"`` (both excluded from the store); seeded once
  by the first refresh, never overwritten,
- ``packages.json`` — every repository's record, plus the channel and
  metapackage versions; this is what the dashboards consume,
- ``package_list.json`` — the package universe (skare3 recipes + organization
  repositories), unfiltered,
- ``test_results.json`` — the digested latest regression-test results,
- ``test_logs/`` — all test-results runs (see :ref:`test_results`),
- ``meta/`` — producer bookkeeping (change-detection state, lock).

Every file is written atomically, so readers (including rsync'd copies) never
see a half-written file.

One copy of each record
-----------------------

``packages.json`` holds each repository's record exactly once: there is no
per-repository tree beside it that could drift out of sync. This file is incrementally
updated by the ``skare3-refresh`` script.

There are two different recorded versions in this file: ``schema_version`` and ``record_version``:


- ``schema_version`` describes the store's *layout*, specifying which files exist and how a reader
  finds things in them. A reader of another version declines the store rather than half-reading it.
- ``record_version`` (with ``record_options``) describes the shape of one repository record. This is
  what decides whether the producer can reuse the already existing record.

Keeping them apart matters: a layout change must not cost a refetch of every repository, which
would be thousands of GraphQL queries for records that are not invalid.

Package Deployment Status
-------------------------

There are five fields related to the package's deployment status:

- ``master_version`` is the latest version in the ``ska3-masters`` channel.
- ``flight`` is the version pinned by the ``ska3-flight`` metapackage.
- ``matlab`` is the version pinned by the ``ska3-matlab`` metapackage.
- ``aca`` is the version pinned by the ``ska3-aca`` metapackage.
- ``test_version`` is the version used in the latest regression run.
- ``test_status`` is the latest regression run result (pass or fail).

These fields are not directly related to repository activity, so
every refresh recomputes all of them for every repository — including the ones
whose details were not refetched. A ``master_version`` that does not correspond
to the master branch is a CI failure to investigate.

.. automodule:: skare3_tools.packages.store

The recipes
-----------

The package universe comes from the skare3 recipes (``pkg_defs/*/meta.yaml``)
plus the organizations' repository listings. The recipes are fetched as a
tarball of the default branch into a temporary directory, once per run, and
nothing is left behind: there is deliberately no checkout in the data
directory.

If the fetch fails, the store's own ``package_list.json`` is the parsed product
of an earlier fetch and stands in for the recipes. The error is then reported in a summary.
If the fetch fails and there is no ``package_list.json``, the run aborts.

The producer: skare3-refresh
----------------------------

.. automodule:: skare3_tools.packages.refresh

Publishing: skare3-dashboard-update
-----------------------------------

The hourly production job reduces to ``skare3-refresh`` followed by rendering, and "publishing"
amounts to copying the JSON files into the public directory served over HTTP.

.. automodule:: skare3_tools.scripts.dashboard_update

Reading the data: DataClient
----------------------------

.. autoclass:: skare3_tools.packages.DataClient
   :members:

Falling back is decided per file, not once per client: a store or a published
location can be missing one file and be authoritative for the rest — which is
exactly what a store written by an older layout looks like. One absent file
must not send every other read to Github.

The public functions of :mod:`skare3_tools.packages`
(:func:`~skare3_tools.packages.get_repository_info`,
:func:`~skare3_tools.packages.get_repositories_info` and
:func:`~skare3_tools.packages.get_package_list`) read the store through this
client, so they need no Github token. They query Github only when asked for
something the store does not hold — a different ``since``, say — or with
``update=True``. What the store's records were produced with is recorded in
the aggregate itself, and reported by
:func:`~skare3_tools.packages.record_options`.

The dashboard views (``skare3-dashboard``, ``skare3-test-dashboard``) are plain renderers of this
data: they read it through this client, and do not query Github themselves.

Data Service
============

Package and test-result data is consolidated in a single on-disk store,
written by exactly one producer and read by everything else.

The store
---------

The store root is ``CONFIG["data_dir"]`` (``$SKA/data/skare3/skare3_data/data``
on synced hosts, which reaches every machine through the existing ``$SKA/data``
rsync). It holds:

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
- ``test_logs/`` — the test-results runs (see :ref:`test_results`),
- ``meta/`` — producer bookkeeping (change-detection state, lock).

Every file is written atomically, so readers (including rsync'd copies) never
see a half-written file.

One copy of each record
-----------------------

``packages.json`` holds each repository's record exactly once: there is no
per-repository tree beside it that could drift out of sync. A single-repository
read picks the entry out of the aggregate, so every source answers it the same
way, and ``skare3-refresh`` reuses the previous aggregate as its incremental
cache — the output *is* the cache.

Two versions are recorded, and they mean different things. ``schema_version``
describes the store's *layout* — which files exist and how a reader finds
things in them — and a reader of another version declines the store rather
than half-reading it. ``record_version`` (with ``record_options``) describes
the shape of one repository record, and it is what decides whether the producer
can reuse what is already there. Keeping them apart matters: a layout change
must not cost a refetch of every repository, which would be thousands of
GraphQL queries for records that were never invalid.

Deployment stages, not repository properties
--------------------------------------------

Five fields of each record say where the package currently sits in the
pipeline rather than anything about its repository: ``master_version`` (the
latest in the ``ska3-masters`` channel, i.e. what the ``ska3-masters``
environment installs), ``flight``, ``matlab`` and ``aca`` (what the
corresponding metapackages pin), and ``test_version``/``test_status`` (the
version the latest regression run actually exercised, and how it fared).

They move with the channels and the test runs, not with repository pushes, so
every refresh recomputes all of them for every repository — including the ones
whose detail was not refetched. A ``master_version`` that does not correspond
to the master branch is a CI failure to investigate, not a data variant.

.. automodule:: skare3_tools.packages.store

The recipes
-----------

The package universe comes from the skare3 recipes (``pkg_defs/*/meta.yaml``)
plus the organizations' repository listings. The recipes are fetched as a
tarball of the default branch into a temporary directory, once per run, and
nothing is left behind: there is deliberately no checkout in the data
directory, where it would ride the ``$SKA/data`` rsync, could be clobbered by
anything else writing there, and could be silently ``git pull``-ed into
nothing by a caller without write access — all of which happened.

If the fetch fails, the store's own ``package_list.json`` is the parsed product
of an earlier fetch and stands in for the recipes, reported as a failure so the
run is not quietly built on an older universe. With neither, the run aborts.

The producer: skare3-refresh
----------------------------

.. automodule:: skare3_tools.packages.refresh

Reading the data: DataClient
----------------------------

.. autoclass:: skare3_tools.packages.DataClient
   :members:

The dashboard views (``skare3-dashboard``, ``skare3-test-dashboard``) are
plain renderers of this data: the hourly production job reduces to
``skare3-refresh`` followed by rendering, and publishing the JSON is a file
copy.

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

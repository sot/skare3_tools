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
- ``packages.json`` — the aggregate the dashboards consume,
- ``test_results.json`` — the digested latest regression-test results,
- ``repos/{owner}/{name}.json`` — per-repository detail,
- ``test_logs/`` — the test-results runs (see :ref:`test_results`),
- ``meta/`` — producer bookkeeping (change-detection state, lock).

Every file is written atomically, so readers (including rsync'd copies) never
see a half-written file.

.. automodule:: skare3_tools.packages.store

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

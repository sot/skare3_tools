"""
Skare3-tools configuration.

The configuration is automatically set with default values which specify the location of the skare3
repository, the different conda channels used, the Github organizations who own the packages, and
the directory where to store cached data. This happens the first time this module is imported.

Normally, a user does not need to do anything except to add an environment variable with the
standard password to conda channels called CONDA_PASSWORD.

The configuration is saved in JSON format, in the data directory:

- specified by the SKARE3_TOOLS_DATA environmental variable,
- or $SKA/data/skare3/skare3_data.

The directory must already exist: it is operational data (on synced hosts it
rides the $SKA/data sync). If it cannot be determined, does not exist, or
needs to be written and is not writable, init fails with a DataDirError saying so.
The one exception is a pending config-version upgrade on a read-only copy
(e.g. a synced host): the upgraded config is kept in memory and not persisted.

Importing this module does not fail for lack of a data directory: commands that only query
Github (e.g. the release scripts on GitHub-hosted runners) do not need one. The configuration
then keeps its defaults, and :func:`data_dir` raises the DataDirError when the store is needed.

The default looks like this:

.. code-block:: JSON

    {
      "config_version": 3,
      "repository": "https://github.com/sot/skare3",
      "conda_channels": {
        "masters": [
          "https://ska:{CONDA_PASSWORD}@cxc.cfa.harvard.edu/mta/ASPECT/ska3-conda/masters"
        ],
        "main": [
          "https://ska:{CONDA_PASSWORD}@cxc.cfa.harvard.edu/mta/ASPECT/ska3-conda/flight"
        ],
        "test": [
          "https://ska:{CONDA_PASSWORD}@cxc.cfa.harvard.edu/mta/ASPECT/ska3-conda/flight",
          "https://ska:{CONDA_PASSWORD}@cxc.cfa.harvard.edu/mta/ASPECT/ska3-conda/test"
        ]
      },
      "organizations": [
        "sot",
        "acisops"
      ],
      "store_url": "https://cxc.cfa.harvard.edu/mta/ASPECT/skare3/dashboard",
      "data_dir": ""
    }

Repository exclusions are not configuration: they live in ``repository_status.json``
at the store root (see :mod:`skare3_tools.packages.store`), so they can change
without a skare3_tools release.


Data Directory
--------------

The data store lives in the ``data`` subdirectory of the configuration directory. That location is
*derived* from the environment on every run, and stored empty in ``config.json``: the configuration
file sits inside the store and is copied with it (the ``$SKA/data`` rsync), so a path written by the
producing machine would otherwise follow the files onto every other machine. A ``data_dir`` found in
the configuration that is not inside this machine's data root is ignored for that reason. To point
skare3_tools at a different store, set ``SKARE3_TOOLS_DATA``, which does not travel with the data,
or pass ``--data-dir`` to the commands that accept it.

Conda Channels
---------------

Conda channels are specified as a dictionary, with identifying strings as keys, and list of URL
strings as values:

.. code-block:: JSON

    {
      "conda_channels": {
        "masters": [
          "https://ska:{CONDA_PASSWORD}@cxc.cfa.harvard.edu/mta/ASPECT/ska3-conda/masters"
         ],
        "main": [
          "https://ska:{CONDA_PASSWORD}@cxc.cfa.harvard.edu/mta/ASPECT/ska3-conda"
        ]
      },
    }
"""

import json
import logging
import os

# this is just a default config. This gets saved in a file which can be modified later on.
# If the file exists, its values win, but new default keys are merged in and
# obsolete keys dropped when config_version is older (see init).
_DEFAULT_CONFIG = {
    "config_version": 4,
    "repository": "https://github.com/sot/skare3",
    "conda_channels": {
        "masters": [
            "https://ska:{CONDA_PASSWORD}@cxc.cfa.harvard.edu/mta/ASPECT/ska3-conda/masters"
        ],
        "main": [
            "https://ska:{CONDA_PASSWORD}@cxc.cfa.harvard.edu/mta/ASPECT/ska3-conda/flight"
        ],
        "test": [
            "https://ska:{CONDA_PASSWORD}@cxc.cfa.harvard.edu/mta/ASPECT/ska3-conda/flight",
            "https://ska:{CONDA_PASSWORD}@cxc.cfa.harvard.edu/mta/ASPECT/ska3-conda/test",
        ],
    },
    "organizations": ["sot", "acisops"],
    # published data store location, for readers without a local copy
    "store_url": "https://cxc.cfa.harvard.edu/mta/ASPECT/skare3/dashboard",
    "data_dir": "",
}

# keys removed from the config in later versions; dropped on upgrade
# (v3: deprecated_repositories moved to <data_dir>/repository_status.json)
_OBSOLETE_KEYS = ("deprecated_repositories",)


# behavior that must be tested:
# - _app_data_dir_ unit test
# - first-time call to init
# - resetting the config, passing config and not passing config as argument
# - subsequent calls to init


class DataDirError(Exception):
    """The skare3_tools data directory is not set, does not exist, or is not writable."""


def _app_data_dir_():
    if "SKARE3_TOOLS_DATA" in os.environ:
        return os.environ["SKARE3_TOOLS_DATA"]
    if "SKA" in os.environ:
        return os.path.join(os.environ["SKA"], "data", "skare3", "skare3_data")
    raise DataDirError(
        "Could not determine the skare3_tools data directory:\n"
        "the SKA environment variable is not set.\n"
        "Set SKA, or set SKARE3_TOOLS_DATA to the data directory directly."
    )


def _is_another_machines_data_dir(data_dir, app_data_dir):
    """
    Whether a configured ``data_dir`` came from a different machine.

    The store's own configuration file is copied along with the store, so an
    absolute path that is not inside this machine's data root cannot be about
    this machine.
    """
    if not data_dir:
        return False
    root = os.path.abspath(app_data_dir)
    path = os.path.abspath(data_dir)
    return os.path.commonpath([root, path]) != root


def _persistable(config, app_data_dir):
    """
    The configuration as it should be written out.

    ``data_dir`` is stored empty when it is the default for this machine, so
    the file stays valid wherever the store is copied. Only a deliberate
    override -- a directory inside this data root that is not the default --
    is written.
    """
    stored = dict(config)
    if stored.get("data_dir") == os.path.join(app_data_dir, "data"):
        stored["data_dir"] = ""
    return stored


def _replace_config(new_config):
    """
    Replace the contents of CONFIG.

    CONFIG is updated in place, never rebound, because other modules import it by name.
    """
    CONFIG.clear()
    CONFIG.update(new_config)


def data_dir():
    """
    The data store directory.

    :raises DataDirError: if there is no data directory (the message says why).
    """
    if not CONFIG.get("data_dir"):
        raise _data_dir_error or DataDirError("skare3_tools data directory is not set")
    return CONFIG["data_dir"]


def init(config=None, reset=False):
    """
    Initialize config.

    :param config: dict.
        A dictionary with configuration entries (used to "update" the current config, not replace).
    :param reset: bool.
        Flag to "reset" the configuration (from defaults).
    :return:
    """
    app_data_dir = _app_data_dir_()
    if not os.path.isdir(app_data_dir):
        raise DataDirError(
            f"skare3_tools data directory does not exist: {app_data_dir}"
        )
    config_file = os.path.join(app_data_dir, "config.json")
    exists = os.path.exists(config_file)
    upgraded = False
    if exists and not reset:
        with open(config_file) as f:
            _replace_config(json.load(f))
        if CONFIG.get("config_version", 0) < _DEFAULT_CONFIG["config_version"]:
            # merge in default keys added since the file was written
            # (existing values win, except the version itself)
            upgraded = True
            merged = _DEFAULT_CONFIG.copy()
            merged.update(CONFIG)
            merged["config_version"] = _DEFAULT_CONFIG["config_version"]
            for key in _OBSOLETE_KEYS:
                merged.pop(key, None)
            _replace_config(merged)

        if _is_another_machines_data_dir(CONFIG.get("data_dir"), app_data_dir):
            # config.json lives *inside* the data directory and is rsynced with
            # it, so an absolute path outside this machine's data root belongs
            # to whichever machine produced the store. The environment decides
            # where the data is; a per-machine override goes in
            # SKARE3_TOOLS_DATA, which does not travel with the files.
            logging.getLogger("skare3.config").info(
                "ignoring data_dir '%s' from %s: not under %s",
                CONFIG["data_dir"],
                config_file,
                app_data_dir,
            )
            CONFIG["data_dir"] = ""

    if config is not None:
        CONFIG.update(config)
    if reset:
        _replace_config(_DEFAULT_CONFIG)
    # the store location is derived, never taken on trust from a file that
    # travels between machines. It is absolute in memory and stored empty
    # (see _persistable), so it cannot be baked in again.
    if not CONFIG.get("data_dir"):
        CONFIG["data_dir"] = os.path.join(app_data_dir, "data")
    if config or reset or not exists or upgraded:
        if not os.access(app_data_dir, os.W_OK):
            if config or reset or not exists:
                raise DataDirError(
                    f"skare3_tools data directory is not writable: {app_data_dir}"
                )
            # only the version upgrade needs persisting: a read-only copy
            # (e.g. a synced host) keeps the upgraded config in memory
            logging.getLogger("skare3.config").warning(
                "config upgrade not persisted (%s is not writable)", app_data_dir
            )
            return
        if not os.path.exists(CONFIG["data_dir"]):
            os.makedirs(CONFIG["data_dir"])
        with open(config_file, "w") as f:
            json.dump(_persistable(CONFIG, app_data_dir), f, indent=2)


CONFIG = _DEFAULT_CONFIG.copy()

# Commands that only query Github have no data directory, so importing must not fail for
# lack of one. The error is kept, and data_dir() raises it when the store is needed.
_data_dir_error = None
try:
    init()
except DataDirError as error:
    _data_dir_error = error
    _replace_config(_DEFAULT_CONFIG)

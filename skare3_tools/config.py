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
needs to be written and is not writable, init fails with an error saying so.

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


Cache Directory
---------------

The cached data is stored in the same directory as the configuration, unless otherwise specified in
the configuration itself (one can set 'data_dir' in the configuration to some other directory).

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
import os

# this is just a default config. This gets saved in a file which can be modified later on.
# If the file exists, its values win, but new default keys are merged in and
# obsolete keys dropped when config_version is older (see init).
_DEFAULT_CONFIG = {
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


def _app_data_dir_():
    if "SKARE3_TOOLS_DATA" in os.environ:
        return os.environ["SKARE3_TOOLS_DATA"]
    if "SKA" in os.environ:
        return os.path.join(os.environ["SKA"], "data", "skare3", "skare3_data")
    raise Exception(
        "Could not determine the skare3_tools data directory:\n"
        "the SKA environment variable is not set.\n"
        "Set SKA, or set SKARE3_TOOLS_DATA to the data directory directly."
    )


def init(config=None, reset=False):
    """
    Initialize config.

    :param config: dict.
        A dictionary with configuration entries (used to "update" the current config, not replace).
    :param reset: bool.
        Flag to "reset" the configuration (from defaults).
    :return:
    """
    global CONFIG  # noqa: PLW0603
    app_data_dir = _app_data_dir_()
    if not os.path.isdir(app_data_dir):
        raise Exception(f"skare3_tools data directory does not exist: {app_data_dir}")
    config_file = os.path.join(app_data_dir, "config.json")
    exists = os.path.exists(config_file)
    upgraded = False
    if exists and not reset:
        with open(config_file) as f:
            CONFIG = json.load(f)
        if CONFIG.get("config_version", 0) < _DEFAULT_CONFIG["config_version"]:
            # merge in default keys added since the file was written
            # (existing values win, except the version itself)
            upgraded = True
            merged = _DEFAULT_CONFIG.copy()
            merged.update(CONFIG)
            merged["config_version"] = _DEFAULT_CONFIG["config_version"]
            for key in _OBSOLETE_KEYS:
                merged.pop(key, None)
            CONFIG = merged

    if config is not None:
        CONFIG.update(config)
    if config or reset or not exists or upgraded:
        if not os.access(app_data_dir, os.W_OK):
            raise Exception(
                f"skare3_tools data directory is not writable: {app_data_dir}"
            )
        if reset:
            CONFIG = _DEFAULT_CONFIG.copy()
        if "data_dir" not in CONFIG or not CONFIG["data_dir"]:
            CONFIG["data_dir"] = os.path.join(app_data_dir, "data")
        if not os.path.exists(CONFIG["data_dir"]):
            os.makedirs(CONFIG["data_dir"])
        with open(config_file, "w") as f:
            json.dump(CONFIG, f, indent=2)


# this could be replaced by a lazy attribute in shiny
# (https://www.python.org/dev/peps/pep-0562/)
CONFIG = _DEFAULT_CONFIG.copy()
init()

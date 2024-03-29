"""
The configuration is automatically set with default values which specify the location of the skare3
repository, the different conda channels used, the Github organizations who own the packages, and
the directory where to store cached data. This happens the first time this module is imported.

Normally, a user does not need to do anything except to add an environment variable with the
standard password to conda channels called CONDA_PASSWORD.

The configuration is saved in JSON format, in the location:

- specified by the SKARE3_TOOLS_DATA environmental variable,
- or in the directory $SKA/data/skare3/skare3_data

The default looks like this:

.. code-block:: JSON

    {
      "config_version": 1,
      "repository": "https://github.com/sot/skare3",
      "conda_channels": {
        "masters": [
          "https://ska:{CONDA_PASSWORD}@cxc.cfa.harvard.edu/mta/ASPECT/ska3-conda/masters"
        ],
        "main": [
          "https://ska:{CONDA_PASSWORD}@cxc.cfa.harvard.edu/mta/ASPECT/ska3-conda/flight"
        ],
        "dull": [
          "https://ska:{CONDA_PASSWORD}@cxc.cfa.harvard.edu/mta/ASPECT/ska3-conda/flight-2020.12"
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
      "data_dir": ""
    }


Cache Directory
---------------

The cached data is stored in the same directory as the configuration, unless otherwise specified in
the configuration itself (i.e.: one can have the config in ~/.skare3 and set 'data_dir' in this
configuration to some other directory).

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
# If the file exists, this will be ignored unless explicitly resetting.
_DEFAULT_CONFIG = {
    "config_version": 1,
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
    "data_dir": "",
}


# behavior that must be tested:
# - _app_data_dir_ unit test
# - first-time call to init
# - resetting the config, passing config and not passing config as argument
# - subsequent calls to init


def _app_data_dir_():
    ska_data_dir = os.path.join(os.environ["SKA"], "data", "skare3", "skare3_data")
    if "SKARE3_TOOLS_DATA" in os.environ:
        app_data_dir = os.environ["SKARE3_TOOLS_DATA"]
    elif os.path.exists(ska_data_dir):
        app_data_dir = ska_data_dir
    else:
        app_data_dir = None
    return app_data_dir


def init(config=None, reset=False):
    """

    :param config: dict.
        A dictionary with configuration entries (used to "update" the current config, not replace).
    :param reset: bool.
        Flag to "reset" the configuration (from defaults).
    :return:
    """
    global CONFIG
    app_data_dir = _app_data_dir_()
    if app_data_dir is None:
        raise Exception(
            "Could not figure out the location of the skare3_tools configuration.\n"
            "Either create the $SKA/data/skare3/skare3_data directory\n"
            "or set the SKARE3_TOOLS_DATA environmental variable."
        )
    config_file = os.path.join(app_data_dir, "config.json")
    exists = os.path.exists(config_file)
    if exists and not reset:
        with open(config_file) as f:
            CONFIG = json.load(f)

    if config is not None:
        CONFIG.update(config)
    if config or reset or not exists:
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

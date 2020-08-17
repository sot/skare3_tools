import os
import json


# this is just a default config. This gets saved in a file which can be modified later on.
# If the file exists, this will be ignored unless explicitly resetting.
_DEFAULT_CONFIG = {
    'config_version': 1,
    'repository': 'https://github.com/sot/skare3',
    'conda_channels': {
        'masters': ['https://ska:{CONDA_PASSWORD}@cxc.cfa.harvard.edu/mta/ASPECT/ska3-conda/masters'],
        'main': ['https://ska:{CONDA_PASSWORD}@cxc.cfa.harvard.edu/mta/ASPECT/ska3-conda/shiny'],
        'dull': ['https://ska:{CONDA_PASSWORD}@cxc.cfa.harvard.edu/mta/ASPECT/ska3-conda'],
        "test": ["https://ska:{CONDA_PASSWORD}@cxc.cfa.harvard.edu/mta/ASPECT/ska3-conda",
                 "https://ska:{CONDA_PASSWORD}@cxc.cfa.harvard.edu/mta/ASPECT/ska3-conda/test"]
    },
    'organizations': ['sot', 'acisops'],
    'data_dir': '',
}


# behavior that must be tested:
# - _app_data_dir_ unit test
# - first-time call to init
# - resetting the config, passing config and not passing config as argument
# - subsequent calls to init


def _app_data_dir_():
    local_app_data_dir = os.getenv('LOCALAPPDATA')
    home_dir = os.path.expanduser('~')
    if 'SKARE3_TOOLS_DATA' in os.environ:
        app_data_dir = os.environ['SKARE3_TOOLS_DATA']
    elif local_app_data_dir:
        # this is the windows location
        app_data_dir = os.path.join(local_app_data_dir, 'skare3')
    elif os.path.exists(home_dir) and os.access(home_dir, os.W_OK):
        # can use this in linux and Mac OS
        app_data_dir = os.path.join(home_dir, '.skare3')
    else:
        app_data_dir = None
    return app_data_dir


def init(config=None, reset=False):
    global CONFIG
    app_data_dir = _app_data_dir_()
    if app_data_dir is None:
        raise Exception('Could not figure out where to place skare3_tools configuration')
    config_file = os.path.join(app_data_dir, 'config.json')
    exists = os.path.exists(config_file)
    if exists and not reset:
        with open(config_file) as f:
            CONFIG = json.load(f)

    if config is not None:
        CONFIG.update(config)
    if config or reset or not exists:
        if reset:
            CONFIG = _DEFAULT_CONFIG.copy()
        if 'data_dir' not in CONFIG or not CONFIG['data_dir']:
            CONFIG['data_dir'] = os.path.join(app_data_dir, 'data')
        if not os.path.exists(CONFIG['data_dir']):
            os.makedirs(CONFIG['data_dir'])
        with open(config_file, 'w') as f:
            json.dump(CONFIG, f, indent=2)


# this could be replaced by a lazy attribute in shiny
# (https://www.python.org/dev/peps/pep-0562/)
CONFIG = _DEFAULT_CONFIG.copy()
init()

"""
Package information: the data store, its producer, and the legacy direct API.

The public API of the original ``packages`` module is re-exported here, so
``from skare3_tools import packages`` keeps working unchanged.
"""

from .packages import (  # noqa: F401
    NetworkException,
    _get_release_commit,
    dir_access_ok,
    get_all_nodes,
    get_conda_pkg_dependencies,
    get_conda_pkg_info,
    get_package_list,
    get_parser,
    get_repositories_info,
    get_repository_info,
    github,
    json_cache,
    main,
    repository_info_is_outdated,
)

# isort: split
# DataClient builds on .packages and .store, so it imports after them.
from .client import DataClient  # noqa: F401

"""
Package information: the data store, its producer, and the direct Github queries.

The public API of the original ``packages`` module is re-exported here, so
``from skare3_tools import packages`` keeps working unchanged. Those functions
now read the store by default and query Github only when asked to.
"""

from .packages import (  # noqa: F401
    NetworkException,
    RecipesUnavailable,
    _get_release_commit,
    dir_access_ok,
    get_all_nodes,
    get_conda_pkg_dependencies,
    get_conda_pkg_info,
    get_package_list,
    get_repositories_info,
    get_repository_info,
    github,
    record_options,
)

# isort: split
# DataClient builds on .packages and .store, so it imports after them.
from .client import DataClient  # noqa: F401

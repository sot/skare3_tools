from pkg_resources import get_distribution, DistributionNotFound
from setuptools_scm import get_version
import warnings


try:
    try:
        _dist_info = get_distribution(__name__)
        __version__ = _dist_info.version
        # the following fails with a local repo with an egg in it
        assert __file__.lower().startswith(_dist_info.location.lower())
    except (DistributionNotFound, AssertionError):
        # this might be a local git repo
        __version__ = get_version(root="..", relative_to=__file__)
except Exception:
    warnings.warn("Failed to find skare3_tools package version, setting to 0.0.0")
    __version__ = "0.0.0"

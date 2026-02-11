# we do not use ska_helpers.get_version, because skare3_tools is often used in CI workflows where
# ska_helpers is not available, so this is a simplified version of that function.
def _get_version():
    import importlib
    import logging
    import pathlib
    import warnings

    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore", message=r"Module \w+ was already imported", category=UserWarning
        )
        from importlib import resources, metadata  # noqa: I001

    # Get module file for package.
    package = "skare3_tools"
    module_file = importlib.util.find_spec(package).origin

    try:
        # If resources.files(package) appears to be a git repo, then
        # importlib has gotten a "local" distribution and the
        # version just corresponds to whatever version was the
        # last run of "setup.py sdist" or "setup.py bdist_wheel", i.e.
        # unrelated to current version, so use setuptools_scm instead.
        git_dir = resources.files(package).parent / ".git"
        if git_dir.exists() and git_dir.is_dir():
            # importing this here so we do not get a failure if setuptools_scm is not installed
            # and we are not in a git repo
            import setuptools_scm
            version = setuptools_scm.get_version(
                root=pathlib.Path(".."), relative_to=module_file
            )
        else:
            version = metadata.version(package)


    except Exception as exc:
        logging.warning(f"Failed to get version for skare3_tools: {exc}")
        version = "0.0.0"


    return version


__version__ = _get_version()

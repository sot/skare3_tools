#!/usr/bin/env python
"""
Script to wrap the standard skare3 building script.

This script differs in a few ways from the standard build:

* The input is a github repository, and the corresponding conda package name is inferred.
* The package version of some conda packages can be overwritten. This is used when building a
  release candidate (with an added 'rc' at the end of the version) without modifying meta.yml.
* Replace CONDA_PASSWORD in conda channel URLs on the fly (older conda versions failed to do this)
* ensure there are non-empty directories linux-64, osx-64, noarch, and win-64 in the output.

NOTE: Argument order seems to matter. Any argument unknown to this script is passed to ska_builder.
It seems that unknown arguments must be consecutive, and known arguments must be consecutive.
"""

import argparse
import os
import pathlib
import re
import subprocess
import sys
import tempfile


def overwrite_skare3_version(current_version, new_version, pkg_path):
    """
    Replaces `current_version` by `new_version` in the meta.yaml file located at `pkg_path`.

    This is not a general replacement. The version is replaced if:

      - the line matches the pattern "  version: <current_version>"
      - the line matches the pattern "  <pkg_name> ==<current_version>"

    with possible whitespace before/after, or whitespace around the colon or equality operator.

    Note that this function would not replace the version string if the "version" tag and the value
    are not in the same line, even though this is correct yaml syntax.

    :param current_version: str
    :param new_version: str
    :param pkg_path: pathlib.Path
    :return:
    """
    meta_file = pkg_path / "meta.yaml"
    with open(meta_file) as fh:
        lines = fh.readlines()
    for i, line in enumerate(lines):
        m = re.search(r"(\s+)?version(\s+)?:(\s+)?(?P<version>(\S+)+)", line)
        if m:
            version = m.groupdict()["version"]
            version = version.strip('"').strip("'")
            print("comparing {version} and {current_version}")
            if version == str(current_version):
                print(f"    - version: {current_version} -> {new_version}")
                lines[i] = line.replace(current_version, new_version)
        m = re.search(r"(\s+)?(?P<name>\S+)(\s+)?==(\s+)?(?P<version>(\S+)+)", line)
        if m:
            info = m.groupdict()
            if (
                re.match(r"ska3-\S+$", info["name"])
                and info["version"] == current_version
            ):
                print(
                    f'    - {info["name"]} dependency: {current_version} -> {new_version}'
                )
                lines[i] = line.replace(current_version, new_version)

    with open(meta_file, "w") as f:
        for line in lines:
            f.write(line)


"""
Argument order matters. The first "unknown" positional argument is the package.
The rest are included as "unknown" arguments. So the following list of arguments builds ska3-flight:
  ska3-flight --tag master
while this one tries to build master at tag ska3-flight:
  --tag master ska3-flight
To fix this, I can require that packages are specified as a non-positional argument, but that breaks
all current workflows.
"""


def get_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", help="The repository name in format {owner}/{name}")
    parser.add_argument(
        "--ska3-overwrite-version",
        help="the version of the resulting conda package",
        default=None,
    )
    parser.add_argument(
        "--skare3-overwrite-version",
        dest="ska3_overwrite_version",
        help="the version of the resulting conda package",
        default=None,
    )
    parser.add_argument(
        "--skare3-branch", help="The branch to build (default: master", default="master"
    )
    return parser


def main():
    args, unknown_args = get_parser().parse_known_args()

    if args.ska3_overwrite_version:
        """
        the value of  args.ska3_overwrite_version can be of the forms:
        - `<initial-version>:<final-version>`.
        - `<final-version>`.

        In the first case, there is nothing to do. In the second case, we assume that the final
        version is the same as the final version but removing the release candidate part
        (i.e.: something that looks like "rcN" or "aN" or "bN").
        """
        if ":" not in args.ska3_overwrite_version:
            rc = re.match(
                r"""(?P<version>
                    (?P<release>\S+)     # release segment (usually N!N.N.N but not enforced here)
                    (a|b|rc)[0-9]+       # pre-release segment (rcN, aN or bN, required)
                    (\+(?P<label>\S+))?  # label fragment (an optional string)
                )$""",
                args.ska3_overwrite_version,
                re.VERBOSE,
            )
            if not rc:
                raise Exception(
                    f"wrong format for ska3_overwrite_version: "
                    f"{args.ska3_overwrite_version}"
                )
            version_info = rc.groupdict()
            version_info["label"] = (
                f'+{version_info["label"]}' if version_info["label"] else ""
            )
            args.ska3_overwrite_version = (
                f'{version_info["release"]}{version_info["label"]}'
                f':{version_info["version"]}'
            )

    print("skare3 build args:", args)
    print("skare3 build unknown args:", unknown_args)

    package = args.package.split("/")[-1]

    # these are packages whose name does not match the repository name
    # at this point, automated builds do not know the package name,
    # just the repository name, and the package name determines where to
    # get the configuration.
    package_map = {
        "cmd_states": "Chandra.cmd_states",
        "eng_archive": "Ska.engarchive",
    }
    if package in package_map:
        package = package_map[package]

    print(f"Building {package}")

    # setup condarc, because conda does not seem to replace the env variables
    if "CONDA_PASSWORD" in os.environ:
        condarc = pathlib.Path.home() / ".condarc"
        condarc_in = condarc.with_suffix(".in")
        condarc.replace(condarc_in)
        with open(condarc_in) as condarc_in, open(condarc, "w") as condarc:
            for line in condarc_in.readlines():
                condarc.write(
                    line.replace("${CONDA_PASSWORD}", os.environ["CONDA_PASSWORD"])
                )
    else:
        print(
            "Conda password needs to be given"
            " as environmental variable CONDA_PASSWORD"
        )
        sys.exit(100)

    tmp_dir = pathlib.Path("tmp")
    if not tmp_dir.exists():
        tmp_dir.mkdir()
    with tempfile.TemporaryDirectory(dir=tmp_dir) as tmp_dir:
        tmp_path = pathlib.Path(tmp_dir)
        skare3_path = tmp_path / "skare3"
        print(f"skare3_path: {skare3_path}")

        # fetch skare3
        subprocess.check_call(
            ["git", "clone", "https://github.com/sot/skare3.git"],
            cwd=skare3_path.parent,
        )
        subprocess.check_call(["git", "checkout", args.skare3_branch], cwd=skare3_path)

        # overwrite version
        if args.ska3_overwrite_version:
            skare3_old_version, skare3_new_version = args.ska3_overwrite_version.split(
                ":"
            )
            print(
                f" - overwriting skare3 version {skare3_old_version} -> {skare3_new_version}"
            )
            overwrite_skare3_version(
                skare3_old_version,
                skare3_new_version,
                skare3_path / "pkg_defs" / package,
            )

        # do the actual building
        cmd = (
            ["python", "ska_builder.py", "--github-https", "--force"]
            + unknown_args
            + [package]
        )
        print(" ".join(cmd))
        subprocess.check_call(cmd, cwd=skare3_path)
        print("SKARE3 conda process finished")

        # move resulting files to work dir
        build_dir = pathlib.Path("builds")
        if not build_dir.exists():
            build_dir.mkdir()
        for d in ["linux-64", "osx-64", "osx-arm64", "noarch", "win-64"]:
            print(d)
            d_from = skare3_path / "builds" / d
            d_to = build_dir / d
            if not d_to.exists():
                d_to.mkdir()
            # I do this to make sure the directory is not empty
            with open(d_to / ".ensure-non-empty-dir", "w"):
                pass
            if d_from.exists():
                print(f"SKARE3 moving {d_from} -> {d_to}")
                for filename in d_from.glob("*.bz2"):
                    filename2 = d_to / filename.name
                    filename.replace(filename2)
                for filename in d_from.glob("*.conda"):
                    filename2 = d_to / filename.name
                    filename.replace(filename2)
        print("SKARE3 done")
        for f in build_dir.glob("*/*json*"):
            f.unlink()

        # report result
        files = (
            list(build_dir.glob("linux-64/*tar.bz2*"))
            + list(build_dir.glob("osx-64/*tar.bz2*"))
            + list(build_dir.glob("osx-arm64/*tar.bz2*"))
            + list(build_dir.glob("noarch/*tar.bz2*"))
            + list(build_dir.glob("win-64/*tar.bz2*"))
        )
        files += (
            list(build_dir.glob("linux-64/*conda*"))
            + list(build_dir.glob("osx-64/*conda*"))
            + list(build_dir.glob("osx-arm64/*conda*"))
            + list(build_dir.glob("noarch/*conda*"))
            + list(build_dir.glob("win-64/*conda*"))
        )
        files_str = " ".join([str(f) for f in files])

        print(f"Built files: {files_str}")

        # this output defines variables 'files'
        if "GITHUB_OUTPUT" in os.environ:
            mode = "r+" if os.path.exists(os.environ["GITHUB_OUTPUT"]) else "w"
            with open(os.environ["GITHUB_OUTPUT"], mode) as fh:
                fh.write(f"files={files_str}\n")

        # this output will show up in the workflow summary
        if "GITHUB_STEP_SUMMARY" in os.environ:
            mode = "r+" if os.path.exists(os.environ["GITHUB_STEP_SUMMARY"]) else "w"
            with open(os.environ["GITHUB_STEP_SUMMARY"], mode) as fh:
                fh.write(f"## Files\n")
                for filename in files:
                    fh.write(f"- {filename}\n")


if __name__ == "__main__":
    main()

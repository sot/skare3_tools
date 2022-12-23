Skare3 Conda Package Builder Image
==================================

The built package can be found in the [repository packages](https://github.com/sot/skare3/packages).


Updating the package
--------------------

To update the package, you build it locally and then upload it to the repository.

### Build:

Check what is the latest version, make sure you choose a different one. The CONDA_PASSWORD in this step is the one to access the conda repo on cxc.

    docker build -t docker.pkg.github.com/sot/skare3/centos7-builder:<version> --build-arg CONDA_PASSWORD=<password> .

### Test:

To test, choose a repository to build (e.g. sot/ska_sun) and a tag (can be a commit hash). Use your github username and token in this step (the one used in CI is set in the workflow and secrets):

    export GIT_USERNAME=<username>
    export GIT_PASSWORD=$GITHUB_TOKEN
    mkdir workspace
    docker run --rm  -v `pwd`/workspace:/github/workspace -w /github/workspace -e CONDA_PASSWORD -e GIT_USERNAME -e GIT_PASSWORD docker.pkg.github.com/sot/skare3/centos7-builder:<version> <repository> --tag <tag>

### Authenticate:

You need a Github token with permission to upload packages (a classic token with write:packages scope will do).

    echo $GITHUB_TOKEN | docker login https://docker.pkg.github.com -u <username> --password-stdin

### Upload:

    docker tag docker.pkg.github.com/sot/skare3/centos7-builder:<version> docker.pkg.github.com/sot/skare3/centos7-builder:latest
    docker push docker.pkg.github.com/sot/skare3/centos7-builder:<version>
    docker push docker.pkg.github.com/sot/skare3/centos7-builder:latest

### Run interactively:

    docker run -v /path/to/my/work/dir:/work  -it --rm docker.pkg.github.com/sot/skare3/centos7-builder:<version>

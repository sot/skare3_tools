Skare3 Conda Package Builder Image
==================================

The built package can be found in the [repository packages](https://github.com/sot/skare3/packages).

To build this:

    docker build -t  . docker.pkg.github.com/sot/skare3/centos5-builder:v1 --build-arg CONDA_PASSWORD=<password>

To upload it:

    docker push docker.pkg.github.com/sot/skare3/centos5-builder:v1

To run:

    docker run -v /path/to/my/work/dir:/work  -it --rm docker.pkg.github.com/sot/skare3/centos5-builder:v1

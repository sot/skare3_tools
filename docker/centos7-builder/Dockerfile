FROM centos:centos7

RUN yum -y install gcc \
                   gcc-c++ \
                   perl \
                   curl \
                   sudo \
                   bzip2 \
                   nano \
                   emacs \
                   openssh-server \
                   openssh-clients \
                   git

# this user ID matches github's VM user uid.
RUN useradd -ms /bin/bash ska -u 1001
RUN echo "ska:ska" | chpasswd && usermod -aG wheel ska && echo "%wheel        ALL=(ALL)       NOPASSWD: ALL" >> /etc/sudoers && echo "Defaults:ska        !requiretty" >> /etc/sudoers

USER ska
ENV PS1=' \u \w>'
WORKDIR /home/ska

COPY --chown=ska:ska files/condarc.in /home/ska/.condarc
COPY --chown=ska:ska files/git_pass.py /home/ska/git_pass.py
ENV GIT_ASKPASS="/home/ska/git_pass.py"
ENV PATH="/home/ska/miniconda3/bin:$PATH"

RUN curl -O https://repo.anaconda.com/miniconda/Miniconda3-py38_4.8.3-Linux-x86_64.sh && \
    bash Miniconda3-py38_4.8.3-Linux-x86_64.sh -b && \
    rm Miniconda3-py38_4.8.3-Linux-x86_64.sh

# CONDA_PASSWORD must be passed as argument
ARG CONDA_PASSWORD
RUN : "${CONDA_PASSWORD:?Conda password must be given at build time (e.g. --build-arg CONDA_PASSWORD=\$CONDA_PASSWORD).}" && \
    conda create -y -n ska-builder setuptools_scm gitpython conda-build jinja2 pyyaml python=3.8 numpy testr ska_helpers


# using a different INVALIDATE_CACHE value invalidates the cache here (--build-arg INVALIDATE_CACHE=...)
ARG INVALIDATE_CACHE=unknown
RUN conda run -n ska-builder conda install -y jinja2 pyyaml packaging gitpython
RUN conda run -n ska-builder conda install -y -c https://ska:${CONDA_PASSWORD}@cxc.cfa.harvard.edu/mta/ASPECT/ska3-conda/masters -c defaults -c conda-forge skare3_tools
RUN conda init


USER ska
RUN git config --global user.email 'aca@cfa.harvard.edu'
RUN git config --global user.name 'ska'

ENTRYPOINT ["conda", "run", "-n", "ska-builder", "skare3-build"]

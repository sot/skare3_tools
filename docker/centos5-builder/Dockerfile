FROM astj/centos5-vault:latest as centos5

RUN yum -y install gcc \
                   perl \
                   curl \
                   sudo \
                   bzip2 \
                   nano \
                   emacs \
                   openssh-server \
                   openssh-clients

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

FROM centos5 as intermediate
RUN curl -O https://repo.continuum.io/miniconda/Miniconda3-4.3.21-Linux-x86_64.sh && \
    bash Miniconda3-4.3.21-Linux-x86_64.sh -b && \
    rm Miniconda3-4.3.21-Linux-x86_64.sh

# CONDA_PASSWORD gets passed as argument
ARG CONDA_PASSWORD
# then .condarc is created and removed within one step, otherwise the password can be exposed
RUN CONDA_PASSWORD=$CONDA_PASSWORD && \
    sed -i -e "s/\${CONDA_PASSWORD}/${CONDA_PASSWORD}/g" .condarc && \
    conda install python=3.6.2 conda=4.3.21 -q --yes && \
    conda install -q --yes ska3_builder && \
    rm .condarc

FROM centos5 as final
COPY --from=intermediate /home/ska/miniconda3 /home/ska/miniconda3

COPY files/build.sh /home/ska/build-pkg.sh

ENTRYPOINT ["bash"]

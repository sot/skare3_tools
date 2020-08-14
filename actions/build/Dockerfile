FROM docker.pkg.github.com/sot/skare3/centos7-builder:latest

USER ska
RUN git config --global user.email 'aca@cfa.harvard.edu'
RUN git config --global user.name 'ska'

COPY files/build.py /home/ska/build-pkg.py
ENTRYPOINT ["conda", "run", "-n", "ska-builder", "python", "/home/ska/build-pkg.py"]

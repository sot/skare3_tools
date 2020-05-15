FROM docker.pkg.github.com/sot/skare3/centos5-builder:latest

RUN git config --global user.email 'aca@cfa.harvard.edu'
RUN git config --global user.name 'ska'

COPY files/build.py /home/ska/build-pkg.py
ENTRYPOINT ["/home/ska/build-pkg.py"]

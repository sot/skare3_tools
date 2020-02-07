FROM ubuntu:latest

RUN apt-get update && \
    apt-get install python3 python3-pip git -y

# the skare3_tools folder is outside docker's context (when github builds the action)
# so it can't be copied. This is an issue, because the branch/tag to clone must be changed here.
RUN git clone --branch master https://github.com/sot/skare3_tools.git && \
    pip3 install -r ./skare3_tools/requirements.txt && \
    pip3 install ./skare3_tools

# this user ID matches github's VM user uid.
RUN useradd -ms /bin/bash ska -u 1001
USER ska
WORKDIR /home/ska

ENTRYPOINT ["gdrive", "--batch"]

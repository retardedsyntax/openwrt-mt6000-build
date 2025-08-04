# syntax=docker/dockerfile-upstream:master
#################################################

## https://www.docker.com/blog/introduction-to-heredocs-in-dockerfiles/
## ARGS are env vars that are *only available* during the Docker build.
## They can be modified at Docker build time via '--build-arg VAR="something"'.
ARG BASE_IMAGE=openwrt-imagebuilder-base
FROM ${BASE_IMAGE} AS base

## Install the image builder. Use tmpfile so that tar's compression autodetection works.
ARG BUILDER_URL

ARG WORKDIR=/builder
ARG WORKDIR_IMAGEBUILDER=${WORKDIR}/imagebuilder
ARG USER=buildbot
ARG UID=1000
ARG GID=1000

## Create user
RUN groupadd --gid ${GID} ${USER} && \
    useradd \
      --uid ${UID} \
      --gid ${GID} \
      --create-home \
      --no-user-group \
      --shell "/bin/bash" ${USER}

## Create working directories
RUN mkdir -pv ${WORKDIR_IMAGEBUILDER} \
    && chown -vR ${UID}:${GID} ${WORKDIR_IMAGEBUILDER}

## Download and setup imagebuilder
RUN curl -fL "${BUILDER_URL}" -o /tmp/imagebuilder \
    && tar -xvf /tmp/imagebuilder --strip-components=1 -C ${WORKDIR_IMAGEBUILDER}/ \
    && rm -f /tmp/imagebuilder

WORKDIR ${WORKDIR_IMAGEBUILDER}
USER ${USER}
CMD ["/bin/bash"]



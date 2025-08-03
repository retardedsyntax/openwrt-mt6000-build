# syntax=docker/dockerfile-upstream:master
#################################################

## ARGS are env vars that are *only available* during the Docker build.
## They can be modified at Docker build time via '--build-arg VAR="something"'.
ARG REGISTRY=docker.io/library
ARG BASE_IMAGE=debian:bookworm-slim

FROM ${REGISTRY}/${BASE_IMAGE} AS base

ENV TZ='Europe/Helsinki' \
    LC_ALL='C.UTF-8' \
    LANG='en_US.UTF-8' \
    LANGUAGE='en_US:en:C'

## Step 1. Prepare base image.
COPY ./scripts/base.sh /tmp/base.sh
RUN chmod +x /tmp/base.sh && \
  /bin/bash /tmp/base.sh && \
  rm /tmp/base.sh

FROM base as builder

## Step 2. Prepare builder image.
COPY ./scripts/builder.sh /tmp/builder.sh
RUN chmod +x /tmp/builder.sh && \
  /bin/bash /tmp/builder.sh && \
  rm /tmp/builder.sh

ARG BUILDER_WORKDIR=/builder
ARG BUILDER_USER=buildbot
ARG BUILDER_UID=1000
ARG BUILDER_GID=1000

RUN mkdir ${BUILDER_WORKDIR} && \
  chown ${BUILDER_UID}:${BUILDER_GID} ${BUILDER_WORKDIR}

RUN groupadd --gid ${BUILDER_GID} ${BUILDER_USER} && \
    useradd \
      --uid ${BUILDER_UID} \
      --gid ${BUILDER_GID} \
      --no-create-home \
      --no-user-group \
      --shell "/bin/bash" ${BUILDER_USER}
# --create-home --home-dir ${BUILDER_WORKDIR} \
#    && chown ${BUILDER_UID}:${BUILDER_GID} ${BUILDER_WORKDIR}

ENV GCC_COLORS='error=01;31:warning=01;35:note=01;36:caret=01;32:locus=01:quote=01'

WORKDIR ${BUILDER_WORKDIR}
USER ${BUILDER_USER}
CMD ["/bin/bash"]



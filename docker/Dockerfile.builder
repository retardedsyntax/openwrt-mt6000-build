# syntax=docker/dockerfile-upstream:master
#################################################

## ARGS are env vars that are *only available* during the Docker build.
## They can be modified at Docker build time via '--build-arg VAR="something"'.
ARG BASE_IMAGE=openwrt-ib/base:latest

FROM ${BASE_IMAGE}

ARG SCRIPT_NAME=builder.sh
COPY ./scripts /scripts

RUN chmod -R 0755 /scripts \
  && /bin/bash /scripts/${SCRIPT_NAME} \
  && rm -rf /scripts

ARG WORKDIR=/builder
ARG USERNAME=buildbot
ARG UID=1000
ARG GID=1000

RUN groupadd --gid ${GID} ${USERNAME} && \
    useradd --uid ${UID} --gid ${GID} \
      --create-home --home-dir ${WORKDIR} \
      --no-user-group --shell "/bin/bash" ${USERNAME}
#    && chown ${UID}:${GID} ${WORKDIR}

ENV GCC_COLORS='error=01;31:warning=01;35:note=01;36:caret=01;32:locus=01:quote=01'

#RUN <<EOF
#{
#cat <<EOC
##!/usr/bin/env bash
##chown ${UID}:${USER_GID} ${WORKDIR}
#gosu ${USERNAME} "$@"
#EOC
#} > /usr/local/bin/entrypoint.sh
#EOF
#RUN chmod 0755 /usr/local/bin/entrypoint.sh

WORKDIR ${WORKDIR}
USER ${USERNAME}
#ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["/bin/bash"]



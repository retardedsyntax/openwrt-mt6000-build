# syntax=docker/dockerfile-upstream:master
#################################################

ARG REGISTRY=docker.io/library
ARG BASE_IMAGE=debian:12.11-slim

FROM ${REGISTRY}/${BASE_IMAGE} AS base

COPY ./scripts /scripts
RUN chmod -R 0755 /scripts \
  && /scripts/base.sh \
  && rm -rf /scripts

FROM base

ENV TZ='Europe/Helsinki' \
    LC_ALL='C.UTF-8' \
    LANG='en_US.UTF-8' \
    LANGUAGE='en_US:en:C'

COPY ./scripts /scripts
RUN chmod -R 0755 /scripts \
  && /scripts/setup.sh \
  && rm -rf /scripts

ARG WORKDIR=/builder
ARG USERNAME=buildbot
ARG USER_UID=1000
ARG USER_GID=$USER_UID

RUN groupadd --gid ${USER_GID} ${USERNAME} && \
    useradd --uid ${USER_UID} --gid ${USER_GID} \
      --create-home --home-dir ${WORKDIR} \
      --no-user-group --shell "/bin/bash" ${USERNAME} \
    && chown ${USER_UID}:${USER_GID} ${WORKDIR}

ENV GCC_COLORS='error=01;31:warning=01;35:note=01;36:caret=01;32:locus=01:quote=01'

RUN <<EOF
{
cat <<EOC
#!/usr/bin/env bash
#chown ${USER_UID}:${USER_GID} ${WORKDIR}
gosu ${USERNAME} "$@"
EOC
} > /usr/local/bin/entrypoint.sh
EOF
RUN chmod 0755 /usr/local/bin/entrypoint.sh

WORKDIR ${WORKDIR}
USER ${USERNAME}
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["/bin/bash"]



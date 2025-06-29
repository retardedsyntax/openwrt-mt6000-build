#!/usr/bin/env bash

set -euo pipefail

###############################################################################
## Environment setup
###############################################################################

PROG="$0"
SCRIPT_DIR="$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
DOCKERFILE_DIR="${SCRIPT_DIR}/docker"

## Colon Bash built-in
## https://stackoverflow.com/a/3224910

: "${BUILDER_BASE_IMG=debian:12.11-slim}"
: "${BUILDER_TARGET_PREFIX=openwrt-ib}"
: "${BUILDER_TARGET_BASE:=base}"
: "${BUILDER_TARGET_IMG:=builder}"
#: "${IMAGE_TAG:=latest}"

: "${BUILDER_USER:=buildbot}"
: "${BUILDER_WORKDIR:=/builder}"

## Helper to determine if docker is actually podman
function docker_is_podman() {
  docker --version 2>&1 | grep -qc podman
}

#DOCKER_IS_PODMAN=$(docker --version 2>&1 | grep -qc podman && echo true || echo false)
#DOCKER_CMD="docker"
#[[ ${DOCKER_IS_PODMAN-false} ]] && DOCKER_CMD="podman"

function docker_cmd() {
  if docker_is_podman; then
    docker "$@"
  else
    podman "$@"
  fi
}

if docker_is_podman; then
  DOCKER_USER_ARGS="-u $(id -u):$(id -g)"
else
  DOCKER_USER_ARGS="--userns=keep-id"
fi




###############################################################################
## Helper functions

function yell() 
{ 
  printf '%s: %s\n' "$0" "$*" >&2
}

function die() 
{
  yell "$*"; exit 111
}

function try() 
{ 
  "$@" || die "cannot $*" 
}

function warn() 
{ 
  printf 'WARNING: %s: %s\n' "$0" "$*" >&2
}

function error() 
{ 
  printf 'ERROR: %s: %s\n' "$0" "$*" >&2
}

###############################################################################

###############################################################################
## Builder functions

function usage() {
    cat<<EOT
Script to build the dockerized OpenWRT imagebuilder image.

Usage: $PROG COMMAND [OPTIONS]
  COMMAND is one of:
    build              - build Docker image
    base               - build the builder base image
    builder            - build the builder image
    shell              - start shell in the Docker image

  OPTIONS:
  -i IMAGE_TYPE        - image type ('base' or 'builder')
  -t IMAGE_TAG         - image tag (e.g. 'latest')
  -f DOCKERFILE        - path to Dockerfile
  -d MOUNT_DIR         - working directory to mount in the container (default current directory)
  -o DOCKER_OPT        - additional options to pass to Docker
                         (can occur multiple times)
EOT
    exit 0
}

function build_image() {
    [[ $# -lt 3 ]] && die "Missing positional args: <image-type> <tag> <dockerfile>"

    local type="$1"
    local tag="$2"
    local dfile="$3"
    shift 3

    # Assume rest of the args are options for Docker
    #local opts="$*"

    docker_cmd build \
      --build-arg BASE_IMG="${BUILDER_BASE_IMG}" \
      --build-arg UID="$(id -u)" \
      --build-arg GID="$(id -g)" \
      --build-arg USERNAME="${BUILDER_USER}" \
      --build-arg WORKDIR="${BUILDER_WORKDIR}" \
      "$@" \
      -t "${BUILDER_TARGET_PREFIX}/$type:$tag" \
      -f "$dfile" \
      "${DOCKERFILE_DIR}/"
}


## Run a shell in the container, useful for debugging
function run_shell_in_container() {
    [[ $# -lt 2 ]] && die "Missing positional args: <image-type> <mount-dir>"

    local type="$1"
    local dir="$2"
    shift 2

    # Assume rest of the args are options for Docker
    #local opts="$*"

    # shellcheck disable=SC2068 disable=SC2086
    docker_cmd run \
        --rm -it \
        -h "${BUILDER_TARGET_PREFIX}-$type" \
        "${DOCKER_USER_ARGS}" \
        -v "$dir:${BUILDER_WORKDIR}:z" \
        "$@" \
        "${BUILDER_TARGET_PREFIX}/$type" /bin/bash
}

## Parse CLI args
function parse_cmd() {

    ## CLI params
    COMMAND="$1"
    IMAGE_TYPE=
    IMAGE_TAG="latest"
    DOCKERFILE=
    MOUNT_DIR="$(pwd)"
    DOCKER_OPTS=()

    [[ -z "${COMMAND}" ]] && die "Command cannot be empty"
    shift

    while [[ $# -ge 1 ]]; do
        local key="$1"
        case $key in
            -i)
                ! [[ "$2" =~ ^(base|builder)$ ]] && die "Invalid image type: $2"
                IMAGE_TYPE="$2"; shift
                ;;
            -t)
                IMAGE_TAG="$2"; shift
                ;;
            -f)
                ! [[ -f "$2" ]] && die "Invalid dockerfile: $2"
                DOCKERFILE="$2"; shift
                ;;
            -d)
                ! [[ -d "$2" ]] && die "Invalid mount directory: $2"
                MOUNT_DIR="$2"; shift
                ;;
            -o)
                DOCKER_OPTS+=("$2"); shift 
                ;;
            *)
                die "Invalid option: $key";;
        esac
        shift
    done

    case "${COMMAND}" in
         build)
             [[ -z "${IMAGE_TYPE}" ]] && die "Missing image type (base/builder)"
             [[ -z "${IMAGE_TAG}" ]] && die "Missing image tag"
             [[ -z "${DOCKERFILE}" ]] && die "Missing dockerfile"
             build_image "${IMAGE_TYPE}" "${IMAGE_TAG}" "${DOCKERFILE}" "${DOCKER_OPTS[@]}"
             ;;
         base)
             build_image "base" "latest" "./docker/Dockerfile.base" "${DOCKER_OPTS[@]}"
             ;;
         builder)
             build_image "builder" "latest" "./docker/Dockerfile.builder" "${DOCKER_OPTS[@]}"
             ;;
         shell)
             [[ -z "${IMAGE_TYPE}" ]] && die "Missing image type (base/builder)"
             run_shell_in_container "${IMAGE_TYPE}" "${MOUNT_DIR}" "${DOCKER_OPTS[@]}"
             ;;
         *)
            usage "$0"
            # shellcheck disable=2317
            exit 0
            ;;
    esac
}

if [[ $# -lt 1 ]]; then
    usage "$0"
    # shellcheck disable=2317
    exit 1
fi

parse_cmd "$@"

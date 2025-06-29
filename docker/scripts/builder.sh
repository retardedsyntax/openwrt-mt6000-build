#!/bin/bash

## References:
## https://github.com/docker-library/postgres/blob/master/Dockerfile-debian.template
## https://hub.docker.com/_/debian
## https://hub.docker.com/_/ubuntu
## https://github.com/phusion/baseimage-docker
## https://openwrt.org/docs/guide-developer/toolchain/install-buildsystem

set -exuo pipefail

###############################################################################
## Environment setup

PROG="$0"
SCRIPT_DIR="$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

function apt_cleanup() {
  apt-get clean autoclean
  apt-get autoremove -y
  rm -rf /var/lib/apt/lists/*
}

## APT is being run in a script
export DEBIAN_FRONTEND=noninteractive

APT_ARGS=(
    # "-o APT::AutoRemove::RecommendsImportant=false" # Autoremove recommended packages also
    "-o Dpkg::Options::=\"--force-confold\"" # Use old configuration automatically on conflict
    "--no-install-recommends" # Don't install recommended packages
)

function aptget() { apt-get "${APT_ARGS[@]}" "$@"; }

###############################################################################

###############################################################################
## Step 1. Install packages

apt_pkgs=(
    asciidoc
    bash
    binutils
    bison
    build-essential
    bzip2
    ccache
    flex
    g++
    g++-multilib
    gawk
    gcc
    gcc-multilib
    genisoimage
    gettext
    gzip
    help2man 
    intltool
    libdw-dev
    libelf-dev
    libncurses5-dev
    libncursesw5-dev
    libssl-dev
    patch
    perl-modules 
    pv
    pwgen
    python-is-python3
    python3
    python3-cryptography
    python3-dev
    python3-pip
    python3-pyelftools
    python3-setuptools
    python3-venv
    qemu-utils
    signify-openbsd
    subversion
    swig
    tar
    unzip
    xsltproc
    xxd
    zlib1g-dev
    zstd
)

aptget update
aptget install -y "${apt_pkgs[@]}"

###############################################################################

###############################################################################
## Step 2. Cleanup APT

apt_cleanup

###############################################################################
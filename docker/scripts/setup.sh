#!/bin/bash

## References:
## https://github.com/docker-library/postgres/blob/master/Dockerfile-debian.template
## https://hub.docker.com/_/debian
## https://hub.docker.com/_/ubuntu
## https://github.com/phusion/baseimage-docker
## https://openwrt.org/docs/guide-developer/toolchain/install-buildsystem

set -exuo pipefail

###############################################################################

# Apt is being run in a script
: "${DEBIAN_FRONTEND:=noninteractive}"
export DEBIAN_FRONTEND

APT_ARGS=(
    # "-o APT::AutoRemove::RecommendsImportant=false" # Autoremove recommended packages also
    "-o Dpkg::Options::=\"--force-confold\"" # Use old configuration automatically on conflict
    "-o Acquire::ForceIPv4=true" # IPv6 causes issues sometimes with APT
    "--no-install-recommends" # Don't install recommended packages
)

function aptget() { apt-get "${APT_ARGS[@]}" "$@"; }

###############################################################################

###############################################################################
## Step 1. Install packages

apt_pkgs=(
    curl
    file
    git
    git-lfs
    gnupg2
    jq
    nano 
    net-tools
    pv 
    rsync
    tar
    genisoimage
    signify-openbsd
    unzip
    subversion
    asciidoc
    ccache
    bash
    binutils
    qemu-utils
    bison
    build-essential
    bzip2
    flex
    g++
    g++-multilib
    gawk
    gcc
    gcc-multilib
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
    pwgen
    python-is-python3
    python3
    python3-cryptography
    python3-dev
    python3-pip
    python3-pyelftools
    python3-setuptools
    python3-venv
    swig
    wget
    xsltproc
    xxd
    zlib1g-dev
    zstd
    pv
)

aptget update
aptget install -y "${apt_pkgs[@]}"

###############################################################################

###############################################################################
## Step 2. Cleanup

apt-get clean autoclean
apt-get autoremove --yes
rm -rf /var/lib/apt/lists/*

###############################################################################
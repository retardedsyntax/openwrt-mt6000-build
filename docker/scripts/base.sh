#!/bin/bash

## References:
## https://github.com/docker-library/postgres/blob/master/Dockerfile-debian.template
## https://github.com/phusion/baseimage-docker
## https://github.com/openwrt/buildbot/blob/main/docker/buildworker/Dockerfile
## https://hub.docker.com/_/debian
## https://hub.docker.com/_/ubuntu

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

#export "LC_ALL=${LC_ALL='C.UTF-8'}"
#export "LANG=${LANG='C.UTF-8'}"
#export "LANGUAGE=${LANGUAGE='C'}"

APT_ARGS=(
    # "-o APT::AutoRemove::RecommendsImportant=false" # Autoremove recommended packages also
    "-o Dpkg::Options::=\"--force-confold\"" # Use old configuration automatically on conflict
    "-o Acquire::ForceIPv4=true" # IPv6 causes issues sometimes with APT
    "--no-install-recommends" # Don't install recommended packages
)

## Set APT to use IPv4 permanently, if configured
if [[ ${APT_FORCE_IPV4-false} ]]; then
  printf 'Acquire::ForceIPv4 "true";\n' > /etc/apt/apt.conf.d/1000-force-ipv4-transport
fi

function aptget() { apt-get "${APT_ARGS[@]}" "$@"; }


apt_prep_pkgs=(
    apt-transport-https # APT HTTPS transport support
    ca-certificates # APT HTTPS transport support
    software-properties-common # 'add-apt-repository'
    debconf-utils
    #apt-utils
)

locale_pkgs=(
    locales
    #locales-all
    keyboard-configuration
    console-setup
    tzdata
)

## Check if this is Ubuntu or Debian, as only
## Ubuntu has 'language-pack-en' package
RELEASE=$(grep -oP '(?<=^ID=).+' /etc/os-release | tr -d '"')
if [[ "$RELEASE" =~ "ubuntu" ]]; then
  locale_pkgs+=(language-pack-en)
fi

misc_pkgs=(
    curl
    file
    git
    git-lfs
    gnupg2
    gosu # https://github.com/tianon/gosu
    jq
    nano
    nano 
    #net-tools
    rsync
    wget
)

###############################################################################

###############################################################################
## Step 1. Prepare APT and upgrade installed packages
aptget update -y
aptget install -y "${apt_prep_pkgs[@]}"
aptget dist-upgrade -y

###############################################################################

###############################################################################
## Step 2. Setup and configure locales, tzdata, keyboard and console

## Autoconfigure packages during install with 'debconf-set-selections'
{
cat <<EOF
keyboard-configuration	keyboard-configuration/layout	select	Finnish
keyboard-configuration	keyboard-configuration/variant	select	Finnish
keyboard-configuration	keyboard-configuration/layoutcode	string	fi
console-setup	console-setup/charmap47	select	UTF-8
console-setup	console-setup/codeset47	select	# Latin1 and Latin5 - western Europe and Turkic languages
console-setup	console-setup/codesetcode	string	Lat15
console-setup	console-setup/fontface47	select	Terminus
console-setup	console-setup/fontsize	string	8x16
console-setup	console-setup/fontsize-fb47	select	8x16
console-setup	console-setup/fontsize-text47	select	8x16
tzdata	tzdata/Areas	select	Europe
tzdata	tzdata/Zones/Etc	select	UTC
tzdata	tzdata/Zones/Europe	select	Helsinki
EOF
} | debconf-set-selections

## If this file exists, we're likely in "debian:xxx-slim", and locales are thus
## being excluded so we need to remove that exclusion (since we need locales)
if [ -f /etc/dpkg/dpkg.cfg.d/docker ]; then
  if grep -qE '^path-exclude\s+?/usr/share/locale.*' /etc/dpkg/dpkg.cfg.d/docker; then
     sed -ri '/^path-exclude\s+?\/usr\/share\/locale.*/d' /etc/dpkg/dpkg.cfg.d/docker
  fi
fi

aptget install -y "${locale_pkgs[@]}"

## Generate locale files
#cat << EOF >> /etc/locale.gen
#C.UTF-8 UTF-8
#en_US.UTF-8 UTF-8
#fi_FI.UTF-8 UTF-8
#EOF
#locale-gen
localedef -i en_US -c -f UTF-8 -A /usr/share/locale/locale.alias en_US.UTF-8

###############################################################################

###############################################################################
## Step 3. Install misc utilities and cleanup APT

aptget install -y "${misc_pkgs[@]}"
apt_cleanup

###############################################################################
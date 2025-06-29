#!/bin/bash

## References:
## https://github.com/docker-library/postgres/blob/master/Dockerfile-debian.template
## https://hub.docker.com/_/debian
## https://hub.docker.com/_/ubuntu
## https://github.com/phusion/baseimage-docker
## https://github.com/openwrt/buildbot/blob/main/docker/buildworker/Dockerfile

set -exuo pipefail

###############################################################################

# Apt is being run in a script
: "${DEBIAN_FRONTEND:=noninteractive}"
export DEBIAN_FRONTEND

#export "LC_ALL=${LC_ALL='C.UTF-8'}"
#export "LANG=${LANG='C.UTF-8'}"
#export "LANGUAGE=${LANGUAGE='C'}"

APT_ARGS=(
    # "-o APT::AutoRemove::RecommendsImportant=false" # Autoremove recommended packages also
    "-o Dpkg::Options::=\"--force-confold\"" # Use old configuration automatically on conflict
    "-o Acquire::ForceIPv4=true" # IPv6 causes issues sometimes with APT
    "--no-install-recommends" # Don't install recommended packages
)

## Set forcing IPv4 permanently if configured
#if [[ ${APT_FORCE_IPV4-false} ]]; then
#{
#cat <<EOF
#Acquire::ForceIPv4 "true";
#EOF
#} > /etc/apt/apt.conf.d/1000-force-ipv4-transport
#fi

function aptget() { apt-get "${APT_ARGS[@]}" "$@"; }

# Check if this is Ubuntu or Debian
RELEASE=$(grep -oP '(?<=^ID=).+' /etc/os-release | tr -d '"')

###############################################################################

###############################################################################
## Step 1. Prepare APT and upgrade installed packages

pre_pkgs=(
    apt-transport-https # APT HTTPS transport support
    ca-certificates # APT HTTPS transport support
    software-properties-common # 'add-apt-repository'
    debconf-utils
    #apt-utils
)
aptget update
aptget install -y "${pre_pkgs[@]}"
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

# If this file exists, we're likely in "debian:xxx-slim", and locales are thus
# being excluded so we need to remove that exclusion (since we need locales)
if [ -f /etc/dpkg/dpkg.cfg.d/docker ]; then
  if grep -qE '^path-exclude\s+?/usr/share/locale.*' /etc/dpkg/dpkg.cfg.d/docker; then
     sed -ri '/^path-exclude\s+?\/usr\/share\/locale.*/d' /etc/dpkg/dpkg.cfg.d/docker
  fi
fi

apt_pkgs=(
    gosu # https://github.com/tianon/gosu
    locales
    locales-all
    keyboard-configuration
    console-setup
    tzdata
)
[[ "$RELEASE" =~ "ubuntu" ]] && apt_pkgs+=(language-pack-en) # Only Ubuntu has 'language-pack-en' package
aptget install -y "${apt_pkgs[@]}"

## Generate locale files
cat << EOF >> /etc/locale.gen
C.UTF-8 UTF-8
en_US.UTF-8 UTF-8
fi_FI.UTF-8 UTF-8
EOF
locale-gen
#localedef -i en_US -c -f UTF-8 -A /usr/share/locale/locale.alias en_US.UTF-8

###############################################################################


###############################################################################
## Step 3. Cleanup

apt-get clean autoclean
apt-get autoremove --yes
rm -rf /var/lib/apt/lists/*

###############################################################################
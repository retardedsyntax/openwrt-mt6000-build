# -*- coding: utf-8 -*-
import re
import subprocess
from datetime import timedelta
from typing import TYPE_CHECKING, Optional

import attrs
from semver import VersionInfo, parse_version_info

if TYPE_CHECKING:
    pass

IB_BASE_URL = r"https://downloads.openwrt.org/releases/{}/targets/{}/{}/openwrt-imagebuilder-{}-{}-{}.Linux-x86_64.tar.{}"


def _subprocess_run_stdout(command: str) -> Optional[str]:
    result = subprocess.run(command, shell=True, capture_output=True)
    if result.returncode != 0:
        return None
    return result.stdout.decode().rstrip()


@attrs.define(frozen=True)
class TargetConfig:
    profile: str
    release: VersionInfo
    target: str
    subtarget: str
    packages: list[str] = attrs.field(converter=list)
    # removed_packages: list[str] = attrs.field(converter=list)
    disabled_services: list[str] = attrs.field(converter=list)

    @property
    def release_str(self) -> str:
        return f"{self.release.major}.{self.release.minor}.{self.release.patch}"

    @property
    def imagebuilder_url(self) -> str:
        if self.release.major >= 24:
            ext = "zst"
        else:
            ext = "xz"

        url = IB_BASE_URL.format(
            self.release_str,
            self.target,
            self.subtarget,
            self.release_str,
            self.target,
            self.subtarget,
            ext,
        )
        return url

    def image_name(self, basename: str = "openwrt-imagebuilder") -> str:
        return f"{basename}-{self.release_str}-{self.target}-{self.subtarget}"


def strip_whitespace(value: str) -> str:
    # First, remove leading and trailing whitespace.
    value = value.strip()

    # Then, replace multiple whitespaces within the string
    # with a single whitespace.
    value = re.sub(r"\s\s+", " ", value)

    return value


def parse_target_config(cfgpath: str) -> TargetConfig:
    config_dict = {}

    try:
        with open(cfgpath, "r") as f:
            contents = f.read()

            # (?=\r?\n|\r)
            # re.sub(r"(?m)(^#.*[\r?\n|\r])", "", contents)
            # ^[--]{1}.+(?=\r?\n|\r)

            # Step 1. Remove comment lines starting with '#'
            contents = re.sub(r"(?m)(^#.*[\r?\n|\r])", "", contents)

            # Step 2. Remove comments at the end of lines.
            contents = re.sub(r"(#.*)(?=\r?\n|\r)", "", contents)

            # Step 3. Handle possible multiline strings which continue with '\' (Bash-style).
            contents = re.sub(r"(\\[\r?\n|\r]\s+)", "", contents)

            # Match key and value separated with '=' in named groups.
            # r"(?P<key>[\w\d _\-\.]+)=(?:[\'\"])?(?P<value>[\w\d _\-\.]*)(?:[\'\"])?(?:\r?\n|\r)"
            pattern = re.compile(
                r"(?P<key>[\w\d _\-\.]+)=(?:[\'\"])?(?P<value>[\w\d _\-\.]*)(?:[\'\"])?"
            )
            for line in contents.splitlines():
                if match := pattern.match(line):
                    key = strip_whitespace(match["key"])
                    value = strip_whitespace(match["value"])
                    config_dict[key] = value
    except FileNotFoundError:
        pass

    # pkgs = []
    # removed = []
    ## Separate packages
    # for pkg in config_dict.get("OPENWRT_PACKAGES", "").split():
    #    if re.match(r"^[--]{1}.+", pkg):
    #        pkg = re.sub(r"^[--]+", "", pkg)
    #        removed.append(pkg)
    #    else:
    #        pkgs.append(pkg)

    return TargetConfig(
        profile=config_dict.get("OPENWRT_PROFILE", ""),
        release=parse_version_info(config_dict.get("OPENWRT_RELEASE", "")),
        target=config_dict.get("OPENWRT_TARGET", ""),
        subtarget=config_dict.get("OPENWRT_SUBTARGET", ""),
        packages=config_dict.get("OPENWRT_PACKAGES", "").split(),
        disabled_services=(config_dict.get("OPENWRT_DISABLED_SERVICES", "")).split(),
    )


def timedelta_to_dhms(td: timedelta) -> tuple[int, int, int, float]:
    """
    Convert `datetime.timedelta` to days, hours, minutes and seconds.

    :param td: Time delta to convert.
    :type td: timedelta
    :return: Tuple of days, hours, minutes and seconds.
    :rtype: tuple[int, int, int, float]
    """
    days = td.days
    hours, remainder = divmod(td.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    seconds += td.microseconds / 1e6

    return (days, hours, minutes, seconds)

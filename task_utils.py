# -*- coding: utf-8 -*-
import re
import subprocess
from datetime import timedelta
from typing import TYPE_CHECKING, Optional

import attrs
from semver import VersionInfo, parse_version_info

if TYPE_CHECKING:
    pass


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

        return f"https://downloads.openwrt.org/releases/{self.release_str}/targets/{self.target}/{self.subtarget}/openwrt-imagebuilder-{self.release_str}-{self.target}-{self.subtarget}.Linux-x86_64.tar.{ext}"


def _strip_whitespace(value: str) -> str:
    value = value.strip()

    # Remove possible extra whitespace between strings
    value = re.sub(r"\s\s+", " ", value)

    return value


def parse_target_config(cfgpath: str) -> TargetConfig:
    cfg = {}
    pattern = re.compile(
        r"(?<!^#)(?P<key>[\w\d_\-]+)=[\'\"]?(?P<value>[\w\d\s_\-\.]*)[\'\"]?$"
    )

    try:
        with open(cfgpath, "r") as f:
            # Handle multiline strings
            contents = f.read().replace("\\\n", "")
            for line in contents.splitlines():
                if match := pattern.match(line):
                    cfg[_strip_whitespace(match["key"])] = _strip_whitespace(
                        match["value"]
                    )
    except FileNotFoundError:
        pass

    target = TargetConfig(
        profile=cfg["OPENWRT_PROFILE"],
        release=parse_version_info(cfg["OPENWRT_RELEASE"]),
        target=cfg["OPENWRT_TARGET"],
        subtarget=cfg["OPENWRT_SUBTARGET"],
        packages=cfg["OPENWRT_PACKAGES"].split(),
        disabled_services=cfg["OPENWRT_DISABLED_SERVICES"].split(),
    )

    return target


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

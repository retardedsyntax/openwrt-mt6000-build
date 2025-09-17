# -*- coding: utf-8 -*-
import os
import re

import attrs
from semver import VersionInfo, parse_version_info

IMAGEBUILDER_BASE_URL = r"https://downloads.openwrt.org/releases/{}/targets/{}/{}/openwrt-imagebuilder-{}-{}-{}.Linux-x86_64.tar.{}"

REQUIRED_CONFIG_KEYS = [
    "OPENWRT_PROFILE",
    "OPENWRT_RELEASE",
    "OPENWRT_TARGET",
    "OPENWRT_SUBTARGET",
    "OPENWRT_PACKAGES",
]


def join_path(path1: str, path2: str) -> str:
    return os.path.join(path1, path2)


def strip_whitespace(value: str) -> str:
    # First, remove leading and trailing whitespace.
    value = value.strip()

    # Then, replace multiple whitespaces within the string
    # with a single whitespace.
    value = re.sub(r"\s\s+", " ", value)

    return value


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

        url = IMAGEBUILDER_BASE_URL.format(
            self.release_str,
            self.target,
            self.subtarget,
            self.release_str,
            self.target,
            self.subtarget,
            ext,
        )
        return url

    def image_name(self, basename: str = "imagebuilder") -> str:
        return f"openwrt/{basename}-{self.release_str}-{self.target}-{self.subtarget}"


# Handle possible multiline strings which continue with '\' (Bash-style).
# contents = re.sub(r"(\\[\r?\n|\r]\s+)", "", contents)
# Grab text between quotes containing newlines.
# (?m)(?:[\'\"])([^\'\"]+)(?:[\'\"])
# (?m)(?:[\w_\-\.]+)=(?:[\'\"])(?:[\w\d\s\\_\-\.]*)(?<=[\w\s])([\\\s]*\r?\n)
# ^(?<!#)(?P<key>[\w_\-\.]+)=(?:[\'\"])?(?P<value>[\w\s\\_\-\.]*)(?:[\'\"])?$
# (?=\r?\n|\r)
# re.sub(r"(?m)(^#.*[\r?\n|\r])", "", contents)
# ^[--]{1}.+(?=\r?\n|\r)


def get_target_config(config_path: str) -> TargetConfig:
    """
    Parse target configuration file.

    :param config_path: Path to target configuration file.
    :type config_path: str
    :raises RuntimeError: If the config does not contain all required keys.
    :raises RuntimeError: If the config has invalid values for required keys.
    :return: Target configuration.
    :rtype: TargetConfig
    """
    if not (config_path or os.path.exists(config_path)):
        raise RuntimeError("Config file not found")

    c = {}

    try:
        with open(config_path, "r") as f:
            contents = f.read()

            # Remove comment lines starting with '#', or comments at the end of the line
            contents = re.sub(r"(^#.*[\r?\n])", "", contents, flags=re.MULTILINE)
            contents = re.sub(r"(#.*)(?=\r?\n)", "", contents)

            # For easier parsing, remove newlines, backwards slashes ('\') and extra spaces
            # within quoted strings. This handles Bash-style multiline strings into more
            # tolerable form.
            # contents = re.sub(r"(?<=[\w\s])([\\\s]*\r?\n)", " ", contents)
            contents = re.sub(
                r"(?:[\"\'])[^\"\']+(?:[\"\'])",
                lambda m: re.sub(r"[\\\r\n\s]+", " ", m.group(0)),
                contents,
            )

            # The actual processing, match key and value separated with '=' in named groups.
            pattern = re.compile(
                r"(?P<key>[\w\-\.]+)=(?:[\'\"])?(?P<value>[\w\s\-\.]*)(?:[\'\"])?"
            )
            for line in contents.splitlines():
                if match := pattern.match(line):
                    k = strip_whitespace(match["key"])
                    v = strip_whitespace(match["value"])
                    c[k] = v
    except FileNotFoundError:
        pass

    # Validate that required config keys are present,
    # and that there are values for each key.
    if not all(k in c.keys() for k in REQUIRED_CONFIG_KEYS):
        raise RuntimeError(
            f"Config file {config_path} does not contain all required keys: {REQUIRED_CONFIG_KEYS}"
        )
    for k in c.keys():
        if k in REQUIRED_CONFIG_KEYS:
            v = c.get(k, None)
            if not v or (isinstance(v, str) and v == ""):
                raise RuntimeError(f"Config key {k} has invalid value: {v}")

    # Maybe not needed?
    # Separate packages to those being installed and those
    # being removed.
    #
    # https://www.compart.com/en/unicode/category/Pd
    # ^[\u002D\u2010].+$

    profile = c.get("OPENWRT_PROFILE")
    release = parse_version_info(c.get("OPENWRT_RELEASE"))
    target = c.get("OPENWRT_TARGET")
    subtarget = c.get("OPENWRT_SUBTARGET")
    packages = c.get("OPENWRT_PACKAGES").split()
    disabled_services = (
        []
        if "OPENWRT_DISABLED_SERVICES" not in c
        else c.get("OPENWRT_DISABLED_SERVICES").split()
    )

    return TargetConfig(
        profile=profile,
        release=release,
        target=target,
        subtarget=subtarget,
        packages=packages,
        disabled_services=disabled_services,
    )


# def _subprocess_run_stdout(command: str) -> Optional[str]:
#    result = subprocess.run(command, shell=True, capture_output=True)
#    if result.returncode != 0:
#        return None
#    return result.stdout.decode().rstrip()
#
# def timedelta_to_dhms(td: timedelta) -> tuple[int, int, int, float]:
#    """
#    Convert `datetime.timedelta` to days, hours, minutes and seconds.
#
#    :param td: Time delta to convert.
#    :type td: timedelta
#    :return: Tuple of days, hours, minutes and seconds.
#    :rtype: tuple[int, int, int, float]
#    """
#    days = td.days
#    hours, remainder = divmod(td.seconds, 3600)
#    minutes, seconds = divmod(remainder, 60)
#    seconds += td.microseconds / 1e6
#
#    return (days, hours, minutes, seconds)

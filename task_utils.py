# -*- coding: utf-8 -*-
import subprocess
import os
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Optional
from configparser import ConfigParser
from semver import Version
import re

if TYPE_CHECKING:
    pass


def _subprocess_run_stdout(command: str) -> Optional[str]:
    result = subprocess.run(command, shell=True, capture_output=True)
    if result.returncode != 0:
        return None
    return result.stdout.decode().rstrip()


def _strip_whitespace(value: str) -> str:
    value = value.strip()

    # Remove possible extra whitespace between strings
    value = re.sub(r"\s\s+", " ", value)

    return value


def parse_config_file(cfgpath: str) -> dict[str, Any]:
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

    return cfg


def parse_semver(version: str) -> Version:
    return Version.parse(version)


def read_config(rootdir: str, filename: str = "config.ini"):
    cfg = ConfigParser()
    try:
        with open(os.path.join(rootdir, filename), "r") as cfgfile:
            cfg.read_file(cfgfile)
    except FileNotFoundError:
        pass

    print(f"config: {cfg}")
    return cfg


def write_config(section: str, key: str, value: str, fpath: str):
    cfg = ConfigParser()
    cfg[section] = dict(key=value)
    with open(fpath, "w") as cfgfile:
        cfg.write(cfgfile)


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


def get_container_platform() -> Optional[str]:
    """
    Get current container platform engine, Docker or Podman.

    :return: Container platform or `None` on failure.
    :rtype: Optional[str]
    """
    result = _subprocess_run_stdout("docker --version")
    if not result:
        return None

    if result.startswith("podman"):
        platform = "podman"
    else:
        platform = "docker"

    # print(f"Container platform: {platform}")
    return platform


def get_container_image_id(image_name: str) -> Optional[str]:
    """
    Get image ID for given container image.

    :param image_name: Container image name.
    :type image_name: str
    :return: Container image ID or `None` on failure.
    :rtype: Optional[str]
    """
    platform = get_container_platform()
    if not platform:
        return None

    result = _subprocess_run_stdout(f"{platform} images -q {image_name}:latest")
    if not result:
        return None

    print(f"Image ID for '{image_name}': {result}")
    return result


def get_image_age(image_id: str) -> Optional[timedelta]:
    """
    Get container image age.

    :param image_id: Container image ID.
    :type image_id: str
    :return: Container image age as `datetime.timedelta` or `None` on failure.
    :rtype: Optional[timedelta]
    """
    platform = get_container_platform()
    if not platform:
        return None

    # Get created timestamp of the image
    result = _subprocess_run_stdout(
        f"{platform} inspect -f '{{{{ .Created }}}}' {image_id}"
    )
    if not result:
        return None

    # Hacky hack, remove part of the timestamp
    # because `strptime` only understands 6 digits
    # in the microsecond part.
    #
    # test = "2025-08-02 16:07:16.299542344 +0000 UTC"
    # test = test[:26] + test[29:]
    timestamp = result[:26] + result[29:]
    imgdate = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S.%f %z %Z")

    return datetime.now(timezone.utc) - imgdate
    # days, hours, minutes, seconds = _timedelta_dhms(
    #    datetime.now(timezone.utc) - imgdate
    # )
    # print(f"Image created {days}d {hours}h {minutes}m {seconds}s ago")

#!/usr/bin/env python3

# -*- coding: utf-8 -*-
from optparse import Option
import os
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Optional

import attrs
import structlog
from invoke.collection import Collection
from invoke.exceptions import Exit
from invoke.tasks import task

from task_utils import (
    get_target_config,
    timedelta_to_dhms,
)

if TYPE_CHECKING:
    from invoke.context import Context

log = structlog.get_logger()


def join_path(p1: str, p2: str) -> str:
    return os.path.join(p1, p2)


# Constants
PROJECT_ROOT = os.path.dirname(__file__)
OUTPUT_DIR = join_path(PROJECT_ROOT, "output")
OVERLAY_DIR = join_path(PROJECT_ROOT, "overlay")
DOCKERFILE_DIR = join_path(PROJECT_ROOT, "docker")

DEFAULT_MAX_AGE = 3
DEFAULT_CONF = "default.conf"

IMAGE_BASE = "ubuntu:22.04"
BASE_DOCKERFILE = "Dockerfile.base"
BASE_IMAGE_NAME = "openwrt-base"

IMAGEBUILDER_DOCKERFILE = "Dockerfile.imagebuilder"
IMAGEBUILDER_IMAGE_NAME = "openwrt-imagebuilder"
IMAGEBUILDER_WORKDIR_ROOT = "/builder"
IMAGEBUILDER_WORKDIR = f"{IMAGEBUILDER_WORKDIR_ROOT}/imagebuilder"
IMAGEBUILDER_USER = "buildbot"

###############################################################################
## Utilities
###############################################################################


def source_path(path: str, source_root: str = PROJECT_ROOT) -> str:
    return join_path(source_root, path)


def target_path(path: str, target_root: str = IMAGEBUILDER_WORKDIR_ROOT) -> str:
    return join_path(target_root, path)


## Check that specified directory exists, create if necessary.
def check_dir(path: str | None = None, root_path: str = PROJECT_ROOT) -> None:
    if path:
        dp = join_path(root_path, path)
        if not os.path.exists(dp):
            os.makedirs(dp)


## Check that required directories exist in the given root path,
## and create them if necessary.
def check_dirs(paths: list[str] = [OUTPUT_DIR], root_path: str = PROJECT_ROOT) -> None:
    # Output directory is required
    if OUTPUT_DIR not in paths:
        paths += OUTPUT_DIR

    for p in paths:
        check_dir(p, root_path)


## Generate platorm-specific mount parameter string.
def create_mount_param(
    platform: str,
    path: str,
    source_root: str = PROJECT_ROOT,
    target_root: str = IMAGEBUILDER_WORKDIR_ROOT,
) -> str | None:
    sp = source_path(path, source_root)
    tp = target_path(path, target_root)

    if not os.path.exists(sp):
        return None
    if platform == "podman":
        return f"--mount 'type=bind,src={sp},dst={tp},relabel=shared'"
    else:
        return f"--mount type=bind,source={sp},destination={tp}"


def create_mount_params(
    platform: str,
    paths: list[str] = [],
    source_root: str = PROJECT_ROOT,
    target_root: str = IMAGEBUILDER_WORKDIR_ROOT,
) -> list[str]:
    mounts = []
    for p in paths:
        res = create_mount_param(platform, p, source_root, target_root)
        if res:
            mounts.append(res)
    return mounts


# @attrs.define(frozen=True)
# class ContainerDetails:
#    id: str
#    age_days: int = attrs.field(default=0)
#    age_hours: int = attrs.field(default=0)
#    age_minutes: int = attrs.field(default=0)
#    age_seconds: float = attrs.field(default=0)
#
#
# def get_container_details(
#    ctx: "Context", platform: str, image_name: str
# ) -> Optional[ContainerDetails]:
#    # Try to find the container
#    container_id = None
#    res = ctx.run(f"{platform} images -q {image_name}:latest", hide=True)
#    if res and not res.failed:
#        out = res.stdout.rstrip()
#        if out and out != "":
#            container_id = out
#
#    if not container_id:
#        log.info(f"No container with name '{image_name}' exists")
#        return None
#
#    log.info(f"Found container ID for name '{image_name}': {container_id}")
#
#    # Check the image age
#    res = ctx.run(
#        f"{platform} inspect -f '{{{{ .Created }}}}' {container_id}", hide=True
#    )
#    if not res or res.failed:
#        return ContainerDetails(container_id)
#
#    stamp = res.stdout.rstrip()
#
#    # Hacky hack, remove part of the timestamp
#    # because `strptime` only understands 6 digits
#    # in the microsecond part.
#    #
#    # test = "2025-08-02 16:07:16.299542344 +0000 UTC"
#    # test = test[:26] + test[29:]
#    stamp = stamp[:26] + stamp[29:]
#    days, hours, minutes, seconds = timedelta_to_dhms(
#        datetime.now(timezone.utc)
#        - datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S.%f %z %Z")
#    )
#    return ContainerDetails(container_id, days, hours, minutes, seconds)


def get_image_id(ctx: "Context", platform: str, image_name: str) -> Optional[str]:
    # Try to find the container
    container_id = None
    res = ctx.run(f"{platform} images -q {image_name}", hide=True, warn=True)
    if res and not res.failed:
        out = res.stdout.rstrip()
        if out and out != "":
            container_id = out

    if not container_id:
        log.info(f"No container with name '{image_name}' found")
        return None
    return container_id


def get_image_datetime(
    ctx: "Context", platform: str, image_name: str
) -> Optional[datetime]:
    res = ctx.run(
        f"{platform} history --format '{{{{ .CreatedAt }}}}' {image_name}",
        hide=True,
        warn=True,
    )
    if res and not res.failed:
        out = res.stdout.rstrip()
        if out and out != "":
            return datetime.strptime(out.splitlines()[0], "%Y-%m-%dT%H:%M:%S%z")

    log.info(f"No date found for '{image_name}'")
    return None


def get_image_timedelta(ctx: "Context", platform: str, image_name: str) -> timedelta:
    dt = get_image_datetime(ctx, platform, image_name)
    if dt:
        return datetime.now(dt.tzinfo) - dt
    return timedelta()


###############################################################################


@task
def check_platform(ctx: "Context") -> None:
    """
    Check which platform we are running, Docker or Podman as
    some command parameters differ even if they are mostly
    compatible.
    """

    res = ctx.run("docker --version", hide=True)
    if not res or res.failed:
        raise Exit(
            "Could not determine container platform (Docker/Podman) - cannot continue!"
        )

    out = res.stdout.rstrip()
    if out.startswith("podman"):
        platform = "podman"
    else:
        platform = "docker"

    # print(f"Container platform: {platform}")

    cfg = ctx.config
    if "platform" not in cfg:
        cfg.platform = platform


@task
def check_prerequisites(ctx: "Context") -> None:
    """
    Check prerequisites like required directories.
    """
    check_dirs()


@task(
    pre=[check_platform],
    iterable=["params"],
    optional=["dockerfile", "max_age", "force", "params"],
    help={
        "dockerfile": "Optional alternative Dockerfile to use (default '{BUILDER_BASE_DOCKERFILE}').",
        "max_age": f"Rebuild the image if the previous is more than N days old (default {DEFAULT_MAX_AGE}).",
        "force": "Force container image rebuild (default 'False').",
        "params": "Optional parameters for container build command.",
    },
)
def baseimage(
    ctx: "Context",
    dockerfile: Optional[str] = BASE_DOCKERFILE,
    max_age: int = DEFAULT_MAX_AGE,
    force: Optional[bool] = False,
    params: Optional[list[str]] = None,
) -> None:
    """
    Build base container image.
    """
    plat = ctx.config.platform
    image_name = BASE_IMAGE_NAME

    # Check if image exists, and if so, check the age
    id = get_image_id(ctx, plat, image_name)
    td = get_image_timedelta(ctx, plat, image_name)
    if not id:
        log.info(f"Image '{image_name}' does not exist, building.")
    elif force:
        log.info(f"Forcing rebuild of image: '{image_name}'")
    elif td.days > max_age:
        log.info(f"Image '{image_name}' is more than {max_age} days old, rebuilding.")
    else:
        log.info(f"Image '{image_name}' exists, skipping.")
        return

    cmd_params = [f"{plat} build"]
    if force:
        cmd_params.append("--no-cache")
    if plat == "podman":
        cmd_params.append("--format=docker")
    cmd_params.append(f"--build-arg IMAGE_BASE='{IMAGE_BASE}'")
    cmd_params.append(f"--tag '{image_name}:latest'")
    cmd_params.append(f"--file '{dockerfile}'")

    if params:
        cmd_params = cmd_params + params

    cmd = " ".join(cmd_params)

    with ctx.cd(DOCKERFILE_DIR):
        log.info(f"Build command: {cmd}")
        ctx.run(cmd, pty=True)


@task(pre=[check_platform])
def check_base_image(ctx: "Context") -> None:
    """
    Check if the base image exists, and rebuild if necessary.
    """
    plat = ctx.config.platform
    image_name = BASE_IMAGE_NAME
    id = get_image_id(ctx, plat, image_name)
    if not id:
        log.info(f"Image '{image_name}' does not exist, building.")
        baseimage(ctx, force=True)


@task(
    pre=[check_platform, check_base_image],
    iterable=["params"],
    optional=["config", "dockerfile", "max_age", "force", "params"],
    help={
        "config": f"Name of the config file to use (default '{DEFAULT_CONF}').",
        "dockerfile": "Optional alternative Dockerfile to use.",
        "max_age": f"Rebuild the image if the previous is more than N days old (default {DEFAULT_MAX_AGE}).",
        "force": "Force container image rebuild (default 'False').",
        "params": "Optional parameters for container build command.",
    },
)
def imagebuilder(
    ctx: "Context",
    config: str = DEFAULT_CONF,
    dockerfile: Optional[str] = None,
    max_age: int = DEFAULT_MAX_AGE,
    force: Optional[bool] = False,
    params: Optional[list[str]] = None,
) -> None:
    """
    Build imagebuilder image.
    """
    plat = ctx.config.platform

    conf = get_target_config(join_path(os.getcwd(), config))
    image_name = conf.image_name(IMAGEBUILDER_IMAGE_NAME)
    dfile = dockerfile if dockerfile else IMAGEBUILDER_DOCKERFILE

    # Check if image exists, and if so, check the age
    id = get_image_id(ctx, plat, image_name)
    td = get_image_timedelta(ctx, plat, image_name)
    if not id:
        log.info(f"Image '{image_name}' does not exist, building.")
    elif force:
        log.info(f"Forcing rebuild of image: '{image_name}'")
    elif td.days > max_age:
        log.info(f"Image '{image_name}' is more than {max_age} days old, rebuilding.")
    else:
        log.info(f"Image '{image_name}' exists, skipping.")
        return

    cmd_params = [f"{plat} build"]
    if force:
        cmd_params.append("--no-cache")
    if plat == "podman":
        cmd_params.append("--format=docker")
    cmd_params.append(f"--build-arg IMAGE_BASE='{BASE_IMAGE_NAME}'")
    cmd_params.append(f"--build-arg BUILDER_URL='{conf.imagebuilder_url}'")
    cmd_params.append(f"--build-arg BUILDER_WORKDIR_ROOT='{IMAGEBUILDER_WORKDIR_ROOT}'")
    cmd_params.append(f"--build-arg BUILDER_WORKDIR='{IMAGEBUILDER_WORKDIR}'")
    cmd_params.append(f"--build-arg BUILDER_USER='{IMAGEBUILDER_USER}'")
    cmd_params.append(f"--build-arg BUILDER_UID='{os.getuid()}'")
    cmd_params.append(f"--build-arg BUILDER_GID='{os.getgid()}'")
    cmd_params.append(f"--tag '{image_name}:latest'")
    cmd_params.append(f"--file '{dfile}'")

    if params:
        cmd_params = cmd_params + params

    cmd = " ".join(cmd_params)

    with ctx.cd(DOCKERFILE_DIR):
        log.info(f"Build command: {cmd}")
        ctx.run(cmd, pty=True)


@task(
    pre=[check_platform, check_prerequisites],
    iterable=["params"],
    optional=["base", "config", "cmd", "workdir", "params"],
    help={
        "base": "Whether to start the shell in base image (default 'False')",
        "config": f"Name of the config file to use (default '{DEFAULT_CONF}').",
        "cmd": "Command to run in the container.",
        "workdir": f"Working directory to mount in the container (default '{PROJECT_ROOT}').",
        "params": "Optional parameters for shell command.",
    },
)
def shell(
    ctx: "Context",
    base: Optional[bool] = False,
    config: str = DEFAULT_CONF,
    cmd: Optional[str] = None,
    workdir: str = PROJECT_ROOT,
    params: Optional[list[str]] = None,
):
    """
    Start a shell in container, to either run a command or to run an interactive shell.
    If `base` is `False`, the `config` parameter is required.
    """
    plat = ctx.config.platform

    uid = os.getuid()
    gid = os.getgid()
    env_params = [
        f"--env '{n}={v}'"
        for n, v in [
            ("UID", uid),
            ("GID", gid),
            ("PLATFORM", plat),
        ]
    ]

    if base:
        image_name = BASE_IMAGE_NAME
        mounts = []
    else:
        conf = get_target_config(join_path(PROJECT_ROOT, config))
        image_name = conf.image_name(IMAGEBUILDER_IMAGE_NAME)
        id = get_image_id(ctx, plat, image_name)
        if not id:
            log.info(f"Image '{image_name}' does not exist.")
            return

        # env_params += [
        #    f"--env '{n}={v}'"
        #    for n, v in [
        #        # ("PROFILE", conf.profile),
        #        # ("PACKAGES", f"{' '.join(conf.packages)}"),
        #        # ("DISABLED_SERVICES", f"{' '.join(conf.disabled_services)}"),
        #        # ("BIN_DIR", f"{to_container_path('output')}"),
        #    ]
        # ]
        mounts = create_mount_params(plat, [OUTPUT_DIR, OVERLAY_DIR], workdir)
        mounts += create_mount_params(plat, [config], workdir, IMAGEBUILDER_WORKDIR)

    # Check required directories
    check_dirs(root_path=workdir)

    # Construct the command
    cmd_params = [f"{plat} run --rm --interactive --tty --hostname '{image_name}' "]
    if plat == "podman":
        cmd_params.append("--userns=keep-id")
    else:
        cmd_params.append(f"-u {uid}:{gid}")
    cmd_params += env_params

    cmd_params += mounts

    if params:
        cmd_params.append(*params)
    cmd_params.append(f"{image_name}:latest")
    cmd_params.append(f"{f'{cmd}' if cmd else 'bash'}")

    command = " ".join(cmd_params)

    log.info(f"Shell command: {command}")
    ctx.run(command, pty=True)


@task(
    pre=[check_platform, check_base_image, check_prerequisites],
    optional=["config", "workdir", "force"],
    help={
        "config": f"Name of the config file to use (default '{DEFAULT_CONF}').",
        "workdir": f"Working directory to mount in the container (default '{PROJECT_ROOT}').",
        "force": "Force image and container image rebuild (default 'False').",
    },
)
def build(
    ctx: "Context",
    config: str = DEFAULT_CONF,
    workdir: str = PROJECT_ROOT,
    force: Optional[bool] = False,
):
    """
    Build the OpenWRT image.
    """
    conf = get_target_config(join_path(PROJECT_ROOT, config))

    log.info(
        f"Target configuration: \n"
        f"\t\t\t\tOPENWRT_PROFILE -> {conf.profile}\n"
        f"\t\t\t\tOPENWRT_RELEASE -> {conf.release}\n"
        f"\t\t\t\tOPENWRT_TARGET -> {conf.target}\n"
        f"\t\t\t\tOPENWRT_SUBTARGET -> {conf.subtarget}\n"
    )

    # Build image if needed
    imagebuilder(ctx, config=config, force=force)

    # Check required directories, overlay is optional
    check_dirs(root_path=workdir)

    # Generate command
    command = (
        f"make -C '{IMAGEBUILDER_WORKDIR}' image "
        f"PROFILE='{conf.profile}' "
        f"PACKAGES='{' '.join(conf.packages)}' "
        f"DISABLED_SERVICES='{' '.join(conf.disabled_services)}' "
        f"BIN_DIR='{target_path('output')}' "
    )

    if os.path.exists(OVERLAY_DIR):
        command += f"FILES='{target_path('overlay')}'"

    # Build the image
    log.info(f"Build command: {command}")
    shell(ctx, config=config, cmd=command, workdir=workdir)


@task(
    pre=[check_platform],
    optional=["config"],
    help={
        "config": f"Name of the config file to use (default '{DEFAULT_CONF}').",
    },
)
def info(
    ctx: "Context",
    config: str = DEFAULT_CONF,
):
    """
    Show imagebuilder info.
    """
    command = f"make -C {IMAGEBUILDER_WORKDIR} info"
    log.info(f"Shell command: {command}")
    shell(ctx, config=config, cmd=command)


@task(
    pre=[check_platform],
    optional=["config"],
    help={
        "config": f"Name of the config file to use (default '{DEFAULT_CONF}').",
    },
)
def clean(
    ctx: "Context",
    config: str = DEFAULT_CONF,
):
    """
    Clean OpenWRT build.
    """
    command = f"make -C {IMAGEBUILDER_WORKDIR} clean"
    log.info(f"Shell command: {command}")
    shell(ctx, config=config, cmd=command)


# Add all tasks to the namespace
ns = Collection(
    check_platform,
    check_prerequisites,
    check_base_image,
    baseimage,
    imagebuilder,
    shell,
    build,
    info,
    clean,
)
# Configure every task to act as a shell command
#   (will print colors, allow interactive CLI)
# Add our extra configuration file for the project
# config = Config(defaults={"run": {"pty": True, "echo": True}, "debug": True})
# ns.configure(config)

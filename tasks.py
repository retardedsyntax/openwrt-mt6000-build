#!/usr/bin/env python3

# -*- coding: utf-8 -*-
import os
import re
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Optional

import structlog
from invoke.collection import Collection
from invoke.exceptions import Exit
from invoke.tasks import task

from utils import (
    get_target_config,
    join_path,
)

if TYPE_CHECKING:
    from invoke.context import Context

log = structlog.get_logger()


# Constants
REGISTRY = "docker.io/library"
ROOT_IMAGE = "ubuntu:22.04"

PROJECT_ROOT = os.path.dirname(__file__)
OUTPUT_DIR = join_path(PROJECT_ROOT, "output")
OVERLAY_DIR = join_path(PROJECT_ROOT, "overlay")
DOCKERFILE_DIR = join_path(PROJECT_ROOT, "docker")

DEFAULT_MAX_AGE = 3
DEFAULT_CONF = "default.conf"


OPENWRT_BASE_IMAGE = "openwrt/base"
OPENWRT_BASE_DOCKERFILE = "Dockerfile.base"

IMAGEBUILDER_DOCKERFILE = "Dockerfile.imagebuilder"
IMAGEBUILDER_IMAGE_NAME = "openwrt-imagebuilder"
IMAGEBUILDER_WORKDIR_ROOT = "/builder"
IMAGEBUILDER_WORKDIR = f"{IMAGEBUILDER_WORKDIR_ROOT}/imagebuilder"
IMAGEBUILDER_USER = "buildbot"

###############################################################################
## Utilities
###############################################################################


def check_create_dir(path: str) -> None:
    """
    Check that specified directory exists, create if necessary.

    :param path: Path, defaults to None
    :type path: str
    """
    if not os.path.exists(path):
        os.makedirs(path)


def mount_param(
    platform: str,
    path: str,
    source_root: str,
    target_root: str,
) -> str:
    """
    Get platform-specific mount parameter string.

    :param platform: Platform.
    :type platform: str
    :param path: Path to mount.
    :type path: str
    :param source_root: Path source root directory.
    :type source_root: str, optional
    :param target_root: Path destination root directory.
    :type target_root: str, optional
    :return: Mount parameter string.
    :rtype: str
    """
    sp = join_path(source_root, path)
    tp = join_path(target_root, path)

    if not os.path.exists(sp):
        return ""
    if platform == "podman":
        return f"--mount 'type=bind,src={sp},dst={tp},relabel=shared'"
    else:
        return f"--mount type=bind,source={sp},destination={tp}"


def create_shell_cmd(
    platform: str,
    hostname: str,
    env_args: Optional[list[tuple[str, Any]]] = None,
    params: Optional[list[str]] = None,
) -> str:
    """
    Get platform-specific image shell command.

    :param platform: Container platform.
    :type platform: str
    :return: Shell command.
    :rtype: str
    """
    p = [
        f"{platform}",
        "run",
        "--rm",
        "--interactive",
        "--tty",
        f"--hostname '{hostname}'",
    ]
    if platform == "podman":
        p.append("--userns=keep-id")
    else:
        p.append(f"-u '{os.getuid()}:{os.getgid()}'")
    if env_args:
        for ea in env_args:
            k, v = ea
            p.append(f"--env {k}='{str(v)}'")
    if params:
        p += params
    return " ".join(p)


def create_imgbuild_cmd(
    platform: str,
    force: bool = False,
    build_args: Optional[list[tuple[str, Any]]] = None,
    params: Optional[list[str]] = None,
) -> str:
    """
    Get platform-specific image build command.

    :param platform: Container platform.
    :type platform: str
    :return: Image build command.
    :rtype: str
    """
    p = [f"{platform}", "build"]
    if platform == "podman":
        p += ["--format=docker"]
    if force:
        p += ["--no-cache"]
    if build_args:
        for ba in build_args:
            k, v = ba
            p.append(f"--build-arg {k}='{str(v)}'")
    if params:
        p += params

    return " ".join(p)


def check_image_exists(ctx: "Context", platform: str, image_name: str) -> Optional[str]:
    """
    Check if container image with specified name exists.

    :param ctx: Invoke context.
    :type ctx: Context
    :param platform: Container platform.
    :type platform: str
    :param image_name: Container image name.
    :type image_name: str
    :return: Container image ID or `None` if not found.
    :rtype: Optional[str]
    """
    cid = None
    res = ctx.run(f"{platform} images -q {image_name}", hide=True, warn=True)
    if res and not res.failed:
        out = res.stdout.rstrip()
        if out and out != "":
            cid = out

    if not cid:
        log.info(f"No container image '{image_name}' found")
        return None
    return cid


def check_image_date(
    ctx: "Context", platform: str, image_name: str
) -> Optional[datetime]:
    """
    Check the creation date of the container image with specified name.

    :param ctx: Invoke context.
    :type ctx: Context
    :param platform: Container platform.
    :type platform: str
    :param image_name: Container image name.
    :type image_name: str
    :return: Container build date or `None` if not found.
    :rtype: Optional[datetime]
    """
    cid = None
    res = ctx.run(f"{platform} images -q {image_name}", hide=True, warn=True)
    if res and not res.failed:
        out = res.stdout.rstrip()
        if out and out != "":
            cid = out

    if not cid:
        log.info(f"No container image '{image_name}' found")
        return None

    res = ctx.run(
        f"{platform} history --format '{{{{ .CreatedAt }}}}' {image_name}",
        hide=True,
        warn=True,
    )
    if res and not res.failed:
        out = res.stdout.rstrip()
        if out and out != "":
            return datetime.strptime(out.splitlines()[0], "%Y-%m-%dT%H:%M:%S%z")
    return None


def get_image_timedelta(ctx: "Context", platform: str, image_name: str) -> timedelta:
    """
    Get timedelta of the container image creation date compared to current date.

    :param ctx: Invoke context.
    :type ctx: Context
    :param platform: Container platform.
    :type platform: str
    :param image_name: Container image name.
    :type image_name: str
    :return: Timedelta to container image creation date, or empty timedelta if not found.
    :rtype: timedelta
    """
    dt = check_image_date(ctx, platform, image_name)
    if dt:
        return datetime.now(dt.tzinfo) - dt
    return timedelta()


def imgname_to_hostname(imgname: str) -> str:
    return re.sub(r"[\\/\._-]", "-", imgname)


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

    log.info(f"Container platform: {platform}")

    cfg = ctx.config
    if "platform" not in cfg:
        cfg.platform = platform


@task(
    pre=[check_platform],
    iterable=["params"],
    optional=["params"],
    help={
        "dockerfile": "Optional alternative Dockerfile to use (default '{BUILDER_BASE_DOCKERFILE}').",
        "max_days": f"Rebuild the image if the previous is more than N days old (default {DEFAULT_MAX_AGE}).",
        "force": "Force container image rebuild (default 'False').",
        "params": "Optional parameters for container build command.",
    },
)
def baseimage(
    ctx: "Context",
    dockerfile: str = OPENWRT_BASE_DOCKERFILE,
    max_days: int = DEFAULT_MAX_AGE,
    force: bool = False,
    params: Optional[list[str]] = None,
) -> None:
    """
    Build base container image.
    """
    platform = ctx.config.platform
    imgname = OPENWRT_BASE_IMAGE

    do_build = False
    img_id = check_image_exists(ctx, platform, imgname)
    timedelta = get_image_timedelta(ctx, platform, imgname)

    if force:
        log.info(f"Forcing (re)build of image: '{imgname}'")
        do_build = True
    elif not img_id:
        log.info(f"Image '{imgname}' does not exist, building.")
        do_build = True
    elif timedelta.days > max_days:
        log.info(f"Image '{imgname}' is more than {max_days} days old, rebuilding.")
    else:
        log.info(
            f"Image '{imgname}' exists and is less than {max_days} days old, skipping."
        )

    if do_build:
        command = create_imgbuild_cmd(
            platform=platform,
            force=force,
            build_args=[("REGISTRY", REGISTRY), ("BASE_IMAGE", ROOT_IMAGE)],
            params=[
                f"--tag '{imgname}'",
                f"--file '{dockerfile}'",
            ]
            + (params or []),
        )

        with ctx.cd(DOCKERFILE_DIR):
            log.info(f"Build command: {command}")
            ctx.run(command, pty=True)


@task(pre=[check_platform])
def check_baseimage(ctx: "Context") -> None:
    """
    Check if the base image exists, and rebuild if necessary.
    """
    if not check_image_exists(ctx, ctx.config.platform, OPENWRT_BASE_IMAGE):
        log.info(f"Image '{OPENWRT_BASE_IMAGE}' does not exist, building.")
        baseimage(ctx, force=True)


@task(
    pre=[check_platform, check_baseimage],
    iterable=["params"],
    optional=["config", "dockerfile", "params"],
    help={
        "config": f"Name of the config file to use (default '{DEFAULT_CONF}').",
        "dockerfile": "Optional alternative Dockerfile to use.",
        "max_days": f"Rebuild the image if the previous is more than N days old (default {DEFAULT_MAX_AGE}).",
        "force": "Force container image rebuild (default 'False').",
        "params": "Optional parameters for container build command.",
    },
)
def imagebuilder(
    ctx: "Context",
    config: str = DEFAULT_CONF,
    dockerfile: Optional[str] = None,
    max_days: int = DEFAULT_MAX_AGE,
    force: bool = False,
    params: Optional[list[str]] = None,
) -> None:
    """
    Build target-specific imagebuilder image.
    """
    platform = ctx.config.platform

    do_build = False
    conf = get_target_config(join_path(os.getcwd(), config))
    imgname = conf.image_name()
    dockerfile = dockerfile if dockerfile else IMAGEBUILDER_DOCKERFILE
    img_id = check_image_exists(ctx, platform, imgname)
    timedelta = get_image_timedelta(ctx, platform, imgname)

    if force:
        log.info(f"Forcing (re)build of image: '{imgname}'")
        do_build = True
    elif not img_id:
        log.info(f"Image '{imgname}' does not exist, building.")
        do_build = True
    elif timedelta.days > max_days:
        log.info(f"Image '{imgname}' is more than {max_days} days old, rebuilding.")
    else:
        log.info(
            f"Image '{imgname}' exists and is less than {max_days} days old, skipping."
        )

    if do_build:
        command = create_imgbuild_cmd(
            platform,
            force,
            [
                ("REGISTRY", "localhost"),
                ("BASE_IMAGE", OPENWRT_BASE_IMAGE),
                ("BUILDER_URL", conf.imagebuilder_url),
                ("BUILDER_WORKDIR_ROOT", IMAGEBUILDER_WORKDIR_ROOT),
                ("BUILDER_WORKDIR", IMAGEBUILDER_WORKDIR),
                ("BUILDER_USER", IMAGEBUILDER_USER),
                ("BUILDER_UID", os.getuid()),
                ("BUILDER_GID", os.getgid()),
            ],
            [
                f"--tag '{imgname}'",
                f"--file '{dockerfile}'",
            ]
            + (params or []),
        )

        with ctx.cd(DOCKERFILE_DIR):
            log.info(f"Build command: {command}")
            ctx.run(command, pty=True)


@task(
    pre=[check_platform],
    iterable=["params"],
    optional=["config", "cmd", "workdir"],
    help={
        "base": "Whether to start the shell in base image (default 'False')",
        "config": f"Name of the config file to use (default '{DEFAULT_CONF}').",
        "command": "Command to run in the container (default 'None', which starts Bash shell.).",
        "workdir": f"Working directory to mount in the container (default '{PROJECT_ROOT}').",
    },
)
def shell(
    ctx: "Context",
    base: bool = False,
    config: str = DEFAULT_CONF,
    command: Optional[str] = None,
    workdir: str = PROJECT_ROOT,
):
    """
    Start a shell in container, to either run a command or to run an interactive shell.
    If `base` is `False`, the `config` parameter is required.
    """
    platform = ctx.config.platform

    if base:
        imgname = OPENWRT_BASE_IMAGE
        env_args = [("PLATFORM", platform), ("UID", os.getuid()), ("GID", os.getgid())]
        mounts = []
    else:
        conf = get_target_config(join_path(workdir, config))
        imgname = conf.image_name()
        img_id = check_image_exists(ctx, platform, imgname)
        if not img_id:
            log.info(f"Image '{imgname}' does not exist.")
            raise Exit(f"Image '{imgname}' does not exist.")

        output_dir = f"output-{conf.profile}"
        check_create_dir(join_path(workdir, output_dir))
        mounts = [
            mount_param(
                platform,
                config,
                workdir,
                IMAGEBUILDER_WORKDIR,
            ),
            mount_param(
                platform,
                output_dir,
                workdir,
                IMAGEBUILDER_WORKDIR_ROOT,
            ),
            mount_param(
                platform,
                OVERLAY_DIR,
                workdir,
                IMAGEBUILDER_WORKDIR_ROOT,
            ),
        ]

        env_args = [
            ("PLATFORM", platform),
            ("UID", os.getuid()),
            ("GID", os.getgid()),
            ("PROFILE", conf.profile),
            ("BIN_DIR", f"{join_path(IMAGEBUILDER_WORKDIR_ROOT, output_dir)}"),
        ]
        # env_args += [
        # ("PACKAGES", f"{' '.join(conf.packages)}"),
        # ("DISABLED_SERVICES", f"{' '.join(conf.disabled_services)}"),
        # ]

    p = mounts
    p.append(f"{imgname}")
    if not command:
        command = "bash"
    else:
        p.append(f"{command}")

    command = create_shell_cmd(
        platform=platform,
        hostname=imgname_to_hostname(imgname),
        env_args=env_args,
        params=p,
    )

    log.info(f"Shell command: {command}")
    ctx.run(command, pty=True)


@task(
    pre=[check_platform, check_baseimage],
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
    force: bool = False,
):
    """
    Build the OpenWRT image.
    """
    conf = get_target_config(join_path(workdir, config))

    log.info(
        f"Target configuration: \n"
        f"\t\t\t\tOPENWRT_PROFILE -> {conf.profile}\n"
        f"\t\t\t\tOPENWRT_RELEASE -> {conf.release}\n"
        f"\t\t\t\tOPENWRT_TARGET -> {conf.target}\n"
        f"\t\t\t\tOPENWRT_SUBTARGET -> {conf.subtarget}\n"
    )

    # Build image if needed
    imagebuilder(ctx, config=config, force=force)

    # Create output directory if needed
    output_dir = f"output-{conf.profile}"
    check_create_dir(join_path(workdir, output_dir))

    # Generate command
    cmd = [
        "make",
        f"-C '{IMAGEBUILDER_WORKDIR}'",
        "image",
        f"PROFILE='{conf.profile}'",
        f"PACKAGES='{' '.join(conf.packages)}'",
        f"DISABLED_SERVICES='{' '.join(conf.disabled_services)}'",
        f"BIN_DIR='{join_path(IMAGEBUILDER_WORKDIR_ROOT, output_dir)}'",
    ]

    if os.path.exists(OVERLAY_DIR):
        cmd.append(f"FILES='{join_path(IMAGEBUILDER_WORKDIR_ROOT, 'overlay')}'")

    # Build the image
    command = " ".join(cmd)
    log.info(f"Build command: {command}")
    shell(ctx, config=config, command=command, workdir=workdir)


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
    command = f"make -C '{IMAGEBUILDER_WORKDIR}' info"
    # log.info(f"Shell command: {command}")
    shell(ctx, config=config, command=command)


@task(
    pre=[check_platform],
    optional=["config"],
    help={
        "config": f"Name of the config file to use (default '{DEFAULT_CONF}').",
        "workdir": f"Working directory to mount in the container (default '{PROJECT_ROOT}').",
    },
)
def clean(
    ctx: "Context",
    config: str = DEFAULT_CONF,
    workdir: str = PROJECT_ROOT,
):
    """
    Clean OpenWRT build.
    """
    conf = get_target_config(join_path(workdir, config))

    command = f"make -C '{IMAGEBUILDER_WORKDIR}' clean"
    # log.info(f"Shell command: {command}")
    shell(ctx, config=config, command=command)

    ctx.run(f"rm -rf {join_path(workdir, f'output-{conf.profile}')}", pty=True)


# Add all tasks to the namespace
ns = Collection(
    check_platform,
    check_baseimage,
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

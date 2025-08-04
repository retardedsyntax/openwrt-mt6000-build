#!/usr/bin/env python3

# -*- coding: utf-8 -*-
import os
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Iterable, Optional

import attrs
import structlog
from invoke.collection import Collection
from invoke.exceptions import Exit
from invoke.tasks import task

from task_utils import (
    parse_target_config,
    timedelta_to_dhms,
)

if TYPE_CHECKING:
    from invoke.context import Context

log = structlog.get_logger()

# Constants
ROOT_DIR = os.path.dirname(__file__)
OVERLAY_DIR = os.path.join(ROOT_DIR, "overlay")
OUTPUT_DIR = os.path.join(ROOT_DIR, "output")
DOCKER_DIR = os.path.join(ROOT_DIR, "docker")

BASE_IMAGE = "ubuntu:22.04"

BUILDER_BASE_DOCKERFILE = "Dockerfile.base"

BUILDER_BASE_IMAGE_BASENAME = "imagebuilder-base"
BUILDER_IMAGE_BASENAME = "openwrt-imagebuilder"

BUILDER_DOCKERFILE = "Dockerfile.builder"
BUILDER_WORKDIR = "/builder"
BUILDER_USER = "buildbot"


def create_dirmounts(platform: str, rootdir: str, dirnames: Iterable[str]) -> str:
    mounts = []

    if platform == "podman":
        mounts.append(
            f"--mount type=bind,src={rootdir},dst={BUILDER_WORKDIR},relabel=shared"
        )
    else:
        mounts.append(
            f"--mount type=bind,source={rootdir},destination={BUILDER_WORKDIR}"
        )

    for d in dirnames:
        dpath = os.path.join(rootdir, d)

        if os.path.exists(dpath):
            if platform == "podman":
                mounts.append(
                    f"--mount type=bind,src={dpath},dst={os.path.join(BUILDER_WORKDIR, d)},relabel=shared"
                )
            else:
                mounts.append(
                    f"--mount type=bind,source={dpath},destination={os.path.join(BUILDER_WORKDIR, d)}"
                )

    return " ".join(mounts) + " "


@attrs.define(frozen=True)
class ContainerDetails:
    id: str
    age_days: int = attrs.field(default=0)
    age_hours: int = attrs.field(default=0)
    age_minutes: int = attrs.field(default=0)
    age_seconds: float = attrs.field(default=0)


def get_container_details(
    ctx: "Context", platform: str, image_name: str
) -> Optional[ContainerDetails]:
    # Try to find the container
    container_id = None
    res = ctx.run(f"{platform} images -q {image_name}:latest", hide=True)
    if res and not res.failed:
        out = res.stdout.rstrip()
        if out and out != "":
            container_id = out

    if not container_id:
        log.info(f"No container with name '{image_name}' exists")
        return None

    log.info(f"Found container ID for name '{image_name}': {container_id}")

    # Check the image age
    res = ctx.run(
        f"{platform} inspect -f '{{{{ .Created }}}}' {container_id}", hide=True
    )
    if not res or res.failed:
        return ContainerDetails(container_id)

    stamp = res.stdout.rstrip()

    # Hacky hack, remove part of the timestamp
    # because `strptime` only understands 6 digits
    # in the microsecond part.
    #
    # test = "2025-08-02 16:07:16.299542344 +0000 UTC"
    # test = test[:26] + test[29:]
    stamp = stamp[:26] + stamp[29:]
    days, hours, minutes, seconds = timedelta_to_dhms(
        datetime.now(timezone.utc)
        - datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S.%f %z %Z")
    )
    return ContainerDetails(container_id, days, hours, minutes, seconds)


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


@task(
    pre=[check_platform],
    iterable=["params"],
    optional=["command", "config", "workdir"],
    help={
        "config": "Name of the config file to use (default 'config.conf').",
        "cmd": "Command to run in the container.",
        "workdir": "Working directory to mount in the container.",
        "params": "Optional parameters for container build command.",
    },
)
def shell(
    ctx: "Context",
    config: str = "config.conf",
    cmd: Optional[str] = None,
    workdir: str = os.getcwd(),
    params: Optional[list[str]] = None,
):
    """
    Start a shell in container, to either run a command or to run an interactive shell.
    """
    plat = ctx.config.platform

    conf = parse_target_config(os.path.join(os.getcwd(), config))
    image_name = (
        f"{BUILDER_IMAGE_BASENAME}-{conf.release_str}-{conf.target}-{conf.subtarget}"
    )

    if not os.path.exists(workdir):
        raise Exit(f"Working directory {workdir} doesn't exist - cannot continue!")

    # Create output directory if not exists, overlay is optional
    output_dir = os.path.join(workdir, "output")
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Env variables for the container
    env_vars = [
        f"--env '{n}={v}'"
        for n, v in [
            ("UID", os.getuid()),
            ("GID", os.getgid()),
            ("PLATFORM", plat),
        ]
    ]

    # Construct the command
    cmd_params = [
        f"{plat} run --rm --interactive --tty --hostname '{image_name}' "
        f"{'--userns=keep-id' if plat == 'podman' else f'-u {os.getuid()}:{os.getgid()}'} "
        f"{' '.join(env_vars)}"
    ]

    # Construct mount params
    if plat == "podman":
        mounts = [
            f"--mount 'type=bind,src={workdir},dst={BUILDER_WORKDIR},relabel=shared'"
        ]
    else:
        mounts = [f"--mount 'type=bind,source={workdir},destination={BUILDER_WORKDIR}'"]

    for d in ["output", "overlay"]:
        dpath = os.path.join(workdir, d)
        if os.path.exists(dpath):
            if plat == "podman":
                mounts.append(
                    f"--mount 'type=bind,src={dpath},dst={os.path.join(BUILDER_WORKDIR, d)},relabel=shared'"
                )
            else:
                mounts.append(
                    f"--mount type=bind,source={dpath},destination={os.path.join(BUILDER_WORKDIR, d)}"
                )
    cmd_params.append(" ".join(mounts))

    if params:
        cmd_params.append(*params)
    cmd_params.append(f"{image_name}:latest {f"bash -c '{cmd}'" if cmd else 'bash'}")

    command = " ".join(cmd_params)

    print(f"Shell command: {command}")
    ctx.run(command, pty=True)


@task(
    pre=[check_platform],
    optional=["workdir", "force"],
    help={
        "config": "Name of the config file to use.",
        "workdir": "Working directory to mount in the container, defaults to current directory.",
        "force": "Force rebuilding.",
    },
)
def build(
    ctx: "Context",
    config: str,
    workdir: str = os.getcwd(),
    force: Optional[bool] = False,
):
    """
    Build specified Docker/Podman image.
    """
    cfg = ctx.config.platform_config
    confpath = os.path.join(os.getcwd(), config)
    target_conf = parse_target_config(confpath)

    print(f"Target configuration: {target_conf}")

    # Build the builder image if needed
    builder_image(
        ctx, cfg.platform, cfg.user.uid, cfg.user.gid, target_conf, force=force
    )

    imgname = f"{BUILDER_IMAGE_BASENAME}-{target_conf.release_str}-{target_conf.target}-{target_conf.subtarget}"

    # Create output directory if not exists, overlay is optional
    if not os.path.exists(os.path.join(workdir, "output")):
        os.makedirs(os.path.join(workdir, "output"))

    # Build the image
    command = (
        f"make -C {BUILDER_WORKDIR} image "
        f"PROFILE={target_conf.profile} "
        f'PACKAGES="{" ".join(target_conf.packages)}" '
        f'DISABLED_SERVICES="{" ".join(target_conf.disabled_services)}" '
        f"{f'FILES={os.path.join(BUILDER_WORKDIR, "overlay")}' if os.path.exists(os.path.join(workdir, 'overlay')) else ''} "
        f"BIN_DIR={os.path.join(BUILDER_WORKDIR, 'output')}"
    )
    print(f"Build command: {command}")
    shell(ctx, image=imgname, cmd=command, workdir=workdir)

    # print("Building {}!".format(config))


@task(
    pre=[check_platform],
    iterable=["params"],
    optional=["dockerfile", "config", "force"],
    help={
        "base": "Build base image (default 'True').",
        "config": "Name of the config file to use (default 'config.conf').",
        "dockerfile": "Optional alternative Dockerfile to use.",
        "max_age": "Rebuild the image if the previous is more than N days old (default 3).",
        "force": "Force container image rebuild (default 'False').",
        "params": "Optional parameters for container build command.",
    },
)
def build_image(
    ctx: "Context",
    base: bool = True,
    dockerfile: Optional[str] = None,
    config: str = "config.conf",
    max_age: int = 3,
    force: Optional[bool] = False,
    params: Optional[list[str]] = None,
) -> None:
    """
    Build specified container image.

    If the `base` parameter is `False`, the `config` parameter must be
    provided, to parse the configuration and determine image name.
    """
    plat = ctx.config.platform

    cmd_params = [f"{plat} build", f"{'--no-cache' if force else ''}"]

    if base:
        image_name = BUILDER_BASE_IMAGE_BASENAME
        cmd_params.append(f"--build-arg BASE_IMAGE={BASE_IMAGE}")
        cmd_params.append(f"--tag {image_name}:latest")
        cmd_params.append(
            f"--file {BUILDER_BASE_DOCKERFILE if not dockerfile else dockerfile}"
        )
    else:
        conf = parse_target_config(os.path.join(os.getcwd(), config))
        image_name = f"{BUILDER_IMAGE_BASENAME}-{conf.release_str}-{conf.target}-{conf.subtarget}"

        cmd_params.append(f"--build-arg BASE_IMAGE={BUILDER_BASE_IMAGE_BASENAME}")
        cmd_params.append(f"--build-arg BUILDER_URL={conf.imagebuilder_url}")
        cmd_params.append(f"--build-arg WORKDIR={BUILDER_WORKDIR}")
        cmd_params.append(f"--build-arg USER={BUILDER_USER}")
        cmd_params.append(f"--build-arg UID={os.getuid()}")
        cmd_params.append(f"--build-arg GID={os.getgid()}")
        cmd_params.append(f"--tag {image_name}:latest")
        cmd_params.append(
            f"--file {BUILDER_DOCKERFILE if not dockerfile else dockerfile}"
        )

    if params:
        cmd_params.append(*params)

    container_details = get_container_details(ctx, plat, image_name)
    do_build = False

    if not container_details or force:
        do_build = True
    else:
        if container_details.age_days <= max_age:
            log.info(f"Image '{image_name}' less than {max_age} days old, skipping")
        elif container_details.age_days > max_age:
            log.info(f"Image '{image_name}' older than {max_age} days, rebuilding")
            do_build = True
        else:
            log.info(f"Image '{image_name}' already exists, skipping")

    if do_build:
        log.info(f"(Re)building image: {image_name}")
        with ctx.cd(DOCKER_DIR):
            command = " ".join(cmd_params)
            log.info(f"Build command: {command}")
            ctx.run(command)


# Add all tasks to the namespace
ns = Collection(
    check_platform,
    build_image,
    build,
    shell,
)
# Configure every task to act as a shell command
#   (will print colors, allow interactive CLI)
# Add our extra configuration file for the project
# config = Config(defaults={"run": {"pty": True, "echo": True}, "debug": True})
# ns.configure(config)

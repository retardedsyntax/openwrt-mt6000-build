#!/usr/bin/env python3

# -*- coding: utf-8 -*-
import getpass
import os
from typing import TYPE_CHECKING, Iterable, Optional

from invoke.collection import Collection
from invoke.config import Config
from invoke.exceptions import Exit
from invoke.tasks import task
from semver import Version

from task_utils import (
    get_container_image_id,
    get_container_platform,
    get_image_age,
    parse_config_file,
    timedelta_to_dhms,
)

if TYPE_CHECKING:
    from invoke.context import Context


# Constants
ROOT_DIR = os.path.dirname(__file__)
OVERLAY_DIR = os.path.join(ROOT_DIR, "overlay")
OUTPUT_DIR = os.path.join(ROOT_DIR, "output")
DOCKER_DIR = os.path.join(ROOT_DIR, "docker")

BUILDER_BASE_IMAGE = "debian:bookworm-slim"
BUILDER_WORKDIR = "/builder"
BUILDER_USER = "buildbot"
BUILDER_IMAGE = "openwrt-imagebuilder"


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


def get_imagebuilder_url(release: str, target: str, subtarget: str) -> str:
    if Version.parse(release).major >= 24:
        ext = "zst"
    else:
        ext = "xz"

    return f"https://downloads.openwrt.org/releases/{release}/targets/{target}/{subtarget}/openwrt-imagebuilder-{release}-{target}-{subtarget}.Linux-x86_64.tar.{ext}"


@task
def configure(ctx: "Context") -> None:
    """
    Create and validate configuration, like
    container engine, local user UID & GID etc.

    Modifies `ctx.config` by adding needed values.
    Must be set as @task(pre=[configure]) on relevant task to take effect.
    """
    cfg = ctx.config

    if "platform_config" not in cfg:
        conf = {
            "platform": get_container_platform(),
            "user": {
                "uname": getpass.getuser(),
                "uid": os.getuid(),
                "gid": os.getgid(),
            },
        }
        cfg.platform_config = conf


@task(
    pre=[configure],
    optional=["max_days", "force"],
    help={
        "max_days": "Rebuild the image if the previous is more than N days old, defaults to 3.",
        "force": "Force building the container image regardless of age.",
    },
)
def image(
    ctx: "Context",
    max_days: int = 3,
    force: Optional[bool] = False,
):
    """
    Build the OpenWRT imagebuilder Docker/Podman image.
    """
    cfg = ctx.config.platform_config
    do_build_image = True

    if image_id := get_container_image_id(BUILDER_IMAGE):
        if td := get_image_age(image_id):
            days, _, _, _ = timedelta_to_dhms(td)

            if days < max_days:
                print(
                    f"Image created less than {max_days} days ago, {'forced rebuild' if force else 'skipping'}"
                )
                do_build_image = force

    if do_build_image:
        with ctx.cd(DOCKER_DIR):
            command = (
                f"{cfg.platform} build "
                f"--build-arg BASE_IMAGE={BUILDER_BASE_IMAGE} "
                f"--build-arg BUILDER_WORKDIR={BUILDER_WORKDIR} "
                f"--build-arg BUILDER_USER={BUILDER_USER} "
                f"--build-arg BUILDER_UID={cfg.user.uid} "
                f"--build-arg BUILDER_GID={cfg.user.gid} "
                f"--tag {BUILDER_IMAGE} "
                f"--file ./Dockerfile"
            )

            # print(f"command: {command}")
            ctx.run(command)


@task(
    pre=[configure],
    optional=["command", "directory"],
    help={
        "cmd": "Command to run in the container.",
        "workdir": "Working directory to mount in the container.",
    },
)
def shell(ctx: "Context", cmd: Optional[str] = None, workdir: str = os.getcwd()):
    """
    Start a shell in container, to either run a command or to run an interactive shell.
    """
    cfg = ctx.config.platform_config

    if cmd:
        container_cmd = f"bash -c '{cmd}'"
    else:
        container_cmd = "bash"

    if not os.path.exists(workdir):
        raise Exit(f"Working directory {workdir} doesn't exist - cannot continue!")

    # Create output directory if not exists, overlay is optional
    output_dir = os.path.join(workdir, "output")
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Env variables for the container
    env_vars = []
    for n, v in [
        ("UID", cfg.user.uid),
        ("GID", cfg.user.gid),
        ("PLATFORM", cfg.platform),
    ]:
        env_vars.append(f"--env '{n}={v}'")
        # env_vars += f"--env '{n}={v}' "

    # Construct the command
    command = f"{cfg.platform} run --rm --interactive --tty --hostname {BUILDER_IMAGE} "
    command += f"{'--userns=keep-id ' if cfg.platform == 'podman' else f'-u {cfg.user.uid}:{cfg.user.gid} '}"
    command += f"{' '.join(env_vars)} "
    command += f"{create_dirmounts(cfg.platform, workdir, ['output', 'overlay'])}"
    command += f"{BUILDER_IMAGE}:latest {container_cmd}"

    # print(f"command: {command}")
    ctx.run(command)


@task(pre=[configure, image], help={"config": "Name of the config file to use."})
def build(ctx: "Context", config: str):
    """
    Build specified Docker/Podman image.
    """
    plat_cfg = ctx.config.platform_config
    conf = parse_config_file(os.path.join(os.getcwd(), config))

    print("Target configuration:")
    for k, v in conf.items():
        print(f"{k}: {v}")

    release = conf["OPENWRT_RELEASE"]
    target = conf["OPENWRT_TARGET"]
    subtarget = conf["OPENWRT_SUBTARGET"]

    url = get_imagebuilder_url(release, target, subtarget)
    print(f"Imagebuilder URL: {url}")

    print("Building {}!".format(config))


# Add all tasks to the namespace
ns = Collection(
    image,
    build,
    shell,
)
# Configure every task to act as a shell command
#   (will print colors, allow interactive CLI)
# Add our extra configuration file for the project
config = Config(defaults={"run": {"pty": True, "echo": True}, "debug": True})
ns.configure(config)

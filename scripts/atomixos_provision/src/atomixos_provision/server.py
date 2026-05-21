"""CLI entry point for atomixos-provision / first-boot-provision."""

import sys
from pathlib import Path

import click

from atomixos_provision.settings import AppSettings

__all__ = ["main"]

DEFAULT_CONFIG_ROOT = Path("/data/config")
DEFAULT_HOST = "172.20.30.1"
DEFAULT_PORT = 8080


@click.group()
def cli() -> None:
    """AtomixOS provisioning CLI."""


@cli.command()
@click.argument("config_root", required=False, type=click.Path(path_type=Path))
@click.option("--host", default=None, help="Listen host.")
@click.option("--port", default=None, type=int, help="Listen port.")
def serve(config_root: Path | None, host: str | None, port: int | None) -> None:
    """Run the provisioning web server."""
    import uvicorn

    from atomixos_provision.app import create_app
    from atomixos_provision.provision import validate_config_root

    env_settings = AppSettings()
    settings = AppSettings(
        config_root=validate_config_root(config_root or env_settings.config_root),
        host=host if host is not None else env_settings.host,
        port=port if port is not None else env_settings.port,
        max_source_bytes=env_settings.max_source_bytes,
    )

    # Resolve logo path: from installed location
    # __file__ = <prefix>/lib/python3.X/site-packages/atomixos_provision/server.py
    # 5 parents up reaches <prefix>/, where share/atomixos/atomixos.png lives
    logo_path = (
        Path(__file__).resolve().parent.parent.parent.parent.parent
        / "share"
        / "atomixos"
        / "atomixos.png"
    )

    app = create_app(settings=settings)
    app.state["logo_path"] = logo_path if logo_path.exists() else None

    sd_socket = _get_systemd_socket()

    if sd_socket is not None:
        try:
            config = uvicorn.Config(app, fd=sd_socket.fileno(), log_level="info")
            server = uvicorn.Server(config)
            import asyncio

            asyncio.run(server.serve())
        finally:
            sd_socket.close()
    else:
        uvicorn.run(app, host=settings.host, port=settings.port, log_level="info")


@cli.command()
@click.argument("config_path", type=click.Path(exists=True, path_type=Path))
def validate(config_path: Path) -> None:
    """Validate a config.toml file or config bundle."""
    from atomixos_provision.provision import validate_config_from_path

    try:
        validate_config_from_path(config_path)
        click.echo(f"Valid: {config_path}")
    except Exception as exc:
        click.echo(f"Invalid: {exc}", err=True)
        sys.exit(1)


@cli.command("import")
@click.argument("source_path", type=click.Path(exists=True, path_type=Path))
@click.argument("config_root", type=click.Path(path_type=Path))
def import_bundle(source_path: Path, config_root: Path) -> None:
    """Import a config bundle from a source path."""
    from atomixos_provision.provision import import_config_from_path

    try:
        import_config_from_path(source_path, config_root)
    except Exception as exc:
        click.echo(f"Import failed: {exc}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("config_root", type=click.Path(path_type=Path))
def recover(config_root: Path) -> None:
    """Recover an interrupted config promotion."""
    from atomixos_provision.activation import recover_config_root
    from atomixos_provision.provision import provisioning_lock, validate_config_root

    config_root = validate_config_root(config_root)
    with provisioning_lock(config_root):
        recover_config_root(config_root)


@cli.command("sync-quadlet")
@click.argument("config_root", type=click.Path(path_type=Path))
@click.argument("quadlet_dir", type=click.Path(path_type=Path))
@click.argument("rootless_dir", required=False, default=None, type=click.Path(path_type=Path))
def sync_quadlet(config_root: Path, quadlet_dir: Path, rootless_dir: Path | None) -> None:
    """Sync quadlet units from provisioned config."""
    from atomixos_provision.quadlet_sync import sync_quadlet_units

    sync_quadlet_units(config_root, quadlet_dir, rootless_dir)


@cli.command("check-health")
@click.argument("config_root", type=click.Path(path_type=Path))
def check_health(config_root: Path) -> None:
    """Check required provisioned services from health-required.json."""
    from atomixos_provision.activation import check_required_services

    failures = check_required_services(config_root)
    if failures:
        click.echo("Required services failed: " + ", ".join(failures), err=True)
        sys.exit(1)


@cli.command("complete-initial")
@click.argument("config_root", type=click.Path(path_type=Path))
def complete_initial(config_root: Path) -> None:
    """Mark initial provisioning promotion complete after first-boot checks."""
    from atomixos_provision.activation import cleanup_rollback
    from atomixos_provision.provision import validate_config_root

    cleanup_rollback(validate_config_root(config_root))


def _get_systemd_socket():
    """Get the systemd-passed socket via sd_listen_fds protocol."""
    import os
    import socket

    listen_pid = os.environ.get("LISTEN_PID")
    listen_fds = os.environ.get("LISTEN_FDS")

    if listen_pid is None or listen_fds is None:
        return None

    try:
        if int(listen_pid) != os.getpid():
            return None
        if int(listen_fds) < 1:
            return None
    except ValueError:
        return None

    fd = 3
    sock = socket.socket(fileno=fd)
    sock.setblocking(True)
    return sock


def main() -> None:
    """Entry point for the atomixos-provision command."""
    cli()

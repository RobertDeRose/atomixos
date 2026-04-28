#!/usr/bin/env python3
import argparse
import email.policy
import html
import io
import json
import os
import pwd
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import textwrap
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

try:
    import tomllib
except ModuleNotFoundError:
    print("python3 with tomllib support is required", file=sys.stderr)
    sys.exit(1)


DEFAULT_CONFIG_DIR = Path("/data/config")
CONFIG_DIR_TOKEN = "${CONFIG_DIR}"
FILES_DIR_TOKEN = "${FILES_DIR}"
GZIP_MAGIC = b"\x1f\x8b"
ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"
APP_RUNTIME_USER = "appsvc"
ROOTLESS_NETWORK_NAME = "atomixos-rootless"
RUNTIME_METADATA_FILENAME = "quadlet-runtime.json"
FIREWALL_INBOUND_FILENAME = "firewall-inbound.json"
CONTAINER_SUFFIX = ".container"
QUADLET_SUFFIXES = {".build", ".container", ".image", ".kube", ".network", ".pod", ".volume"}


class ProvisionError(RuntimeError):
    pass


def validate_name(name: str) -> str:
    if not name or "/" in name or "\x00" in name or "." in name or name in {".", ".."}:
        raise ProvisionError(f"invalid quadlet unit name: {name!r}")
    for char in name:
        if not (char.isalnum() or char in {"_", "-"}):
            raise ProvisionError(f"invalid quadlet unit name: {name!r}")
    return name


def require_mapping(value, path: str):
    if not isinstance(value, dict):
        raise ProvisionError(f"expected table at {path}")
    return value


def require_allowed_keys(value, path: str, allowed: set[str], required: set[str] | None = None):
    table = require_mapping(value, path)
    unexpected = set(table) - allowed
    if unexpected:
        keys = ", ".join(sorted(unexpected))
        raise ProvisionError(f"unsupported keys at {path}: {keys}")

    if required is not None:
        missing = required - set(table)
        if missing:
            keys = ", ".join(sorted(missing))
            raise ProvisionError(f"missing required keys at {path}: {keys}")

    return table


def require_string(value, path: str):
    if not isinstance(value, str) or not value.strip():
        raise ProvisionError(f"expected non-empty string at {path}")
    return value.strip()


def require_string_list(value, path: str):
    if not isinstance(value, list) or not value:
        raise ProvisionError(f"expected non-empty array at {path}")
    result = []
    for idx, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise ProvisionError(f"expected non-empty string at {path}[{idx}]")
        result.append(item.strip())
    return result


def require_bool(value, path: str):
    if not isinstance(value, bool):
        raise ProvisionError(f"expected boolean at {path}")
    return value


def require_port_list(value, path: str):
    if not isinstance(value, list) or not value:
        raise ProvisionError(f"expected non-empty array at {path}")

    ports = []
    for idx, item in enumerate(value):
        if not isinstance(item, int) or isinstance(item, bool) or item < 1 or item > 65535:
            raise ProvisionError(f"expected port integer in range 1..65535 at {path}[{idx}]")
        ports.append(item)
    return ports


def ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)


def maybe_chown_user(path: Path, username: str):
    try:
        user = pwd.getpwnam(username)
    except KeyError:
        return

    os.chown(path, user.pw_uid, user.pw_gid)


def format_scalar(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return value
    raise ProvisionError(f"unsupported scalar value type: {type(value).__name__}")


def substitute_tokens(value: str, config_root: Path):
    return value.replace(CONFIG_DIR_TOKEN, str(config_root)).replace(
        FILES_DIR_TOKEN, str(config_root / "files")
    )


def normalize_directives(directives_table: dict, path: str):
    normalized = {}
    for key, raw_value in directives_table.items():
        values = raw_value if isinstance(raw_value, list) else [raw_value]
        if not values:
            continue

        normalized_values = []
        for idx, value in enumerate(values):
            item_path = f"{path}.{key}[{idx}]" if isinstance(raw_value, list) else f"{path}.{key}"
            if isinstance(value, list) or isinstance(value, dict):
                raise ProvisionError(f"expected scalar value at {item_path}")
            normalized_values.append(value)
        normalized[key] = normalized_values
    return normalized


def rewrite_rootless_publish_port(value: str, container_name: str, warnings: list[str]):
    if value.startswith("["):
        host_end = value.find("]")
        if host_end == -1 or host_end + 1 >= len(value) or value[host_end + 1] != ":":
            return value
        bind_host = value[: host_end + 1]
        remainder = value[host_end + 2 :]
    else:
        parts = value.split(":")
        if len(parts) == 2:
            return f"127.0.0.1:{value}"
        if len(parts) < 3:
            return value
        bind_host = parts[0]
        remainder = ":".join(parts[1:])

    if bind_host in {"127.0.0.1", "127.0.1.1"}:
        return value
    if bind_host in {"localhost", "::1", "[::1]"}:
        return f"127.0.0.1:{remainder}"

    warnings.append(
        f"container.{container_name}.Container.PublishPort rewrote non-loopback bind {value!r} to 127.0.0.1"
    )
    return f"127.0.0.1:{remainder}"


def render_section(section_name: str, directives: dict[str, list], config_root: Path):
    lines = [f"[{section_name}]"]
    for key, values in directives.items():
        for value in values:
            rendered_value = substitute_tokens(value, config_root) if isinstance(value, str) else value
            lines.append(f"{key}={format_scalar(rendered_value)}")
    lines.append("")
    return lines


def render_containers(container_table: dict, config_root: Path):
    rendered = {}
    runtime_units = []
    warnings = []

    if not container_table:
        raise ProvisionError("container must define at least one container")

    for container_name, raw_sections in container_table.items():
        validate_name(container_name)
        container_path = f"container.{container_name}"
        sections = require_allowed_keys(
            raw_sections,
            container_path,
            {"privileged", "Unit", "Container", "Install"},
            {"privileged", "Container"},
        )
        privileged = require_bool(sections.get("privileged"), f"{container_path}.privileged")
        container_directives = normalize_directives(
            require_mapping(sections.get("Container"), f"{container_path}.Container"),
            f"{container_path}.Container",
        )

        image_values = container_directives.get("Image")
        if image_values is None or len(image_values) != 1:
            raise ProvisionError(f"{container_path}.Container.Image must be a single string value")
        require_string(image_values[0], f"{container_path}.Container.Image")

        if privileged:
            if "Network" in container_directives and container_directives["Network"] != ["host"]:
                warnings.append(
                    f"container.{container_name}.Container.Network overridden to host for privileged container"
                )
            container_directives["Network"] = ["host"]
            runtime_mode = "rootful"
        else:
            if "Network" in container_directives:
                warnings.append(
                    f"container.{container_name}.Container.Network overridden to {ROOTLESS_NETWORK_NAME} for rootless container"
                )
            container_directives["Network"] = [ROOTLESS_NETWORK_NAME]
            publish_ports = container_directives.get("PublishPort", [])
            if publish_ports:
                rewritten_ports = []
                for idx, value in enumerate(publish_ports):
                    port_value = require_string(value, f"{container_path}.Container.PublishPort[{idx}]")
                    rewritten_ports.append(rewrite_rootless_publish_port(port_value, container_name, warnings))
                container_directives["PublishPort"] = rewritten_ports
            runtime_mode = "rootless"

        lines = []
        if "Unit" in sections:
            unit_directives = normalize_directives(
                require_mapping(sections["Unit"], f"{container_path}.Unit"),
                f"{container_path}.Unit",
            )
            lines.extend(render_section("Unit", unit_directives, config_root))

        lines.extend(render_section("Container", container_directives, config_root))

        if "Install" in sections:
            install_directives = normalize_directives(
                require_mapping(sections["Install"], f"{container_path}.Install"),
                f"{container_path}.Install",
            )
            lines.extend(render_section("Install", install_directives, config_root))

        filename = f"{container_name}{CONTAINER_SUFFIX}"
        rendered[filename] = "\n".join(lines).rstrip() + "\n"
        runtime_units.append(
            {
                "name": container_name,
                "filename": filename,
                "service": f"{container_name}.service",
                "mode": runtime_mode,
            }
        )

    return rendered, runtime_units, warnings


def load_config(config_path: Path, config_root: Path = DEFAULT_CONFIG_DIR):
    try:
        data = tomllib.loads(config_path.read_text())
    except tomllib.TOMLDecodeError as exc:
        raise ProvisionError(f"invalid TOML in {config_path}: {exc}") from exc

    root = require_allowed_keys(
        data,
        "config",
        {"version", "admin", "firewall", "health", "container"},
        {"version", "admin", "firewall", "health", "container"},
    )

    version = root.get("version")
    if not isinstance(version, int) or isinstance(version, bool) or version != 1:
        raise ProvisionError("version must be integer 1")

    admin = require_allowed_keys(root.get("admin"), "admin", {"ssh_keys"}, {"ssh_keys"})
    ssh_keys = require_string_list(admin.get("ssh_keys"), "admin.ssh_keys")

    firewall = require_allowed_keys(root.get("firewall"), "firewall", {"inbound"}, {"inbound"})
    inbound = require_allowed_keys(
        firewall.get("inbound"),
        "firewall.inbound",
        {"tcp", "udp"},
    )
    if "tcp" not in inbound and "udp" not in inbound:
        raise ProvisionError("firewall.inbound must define tcp and/or udp")
    firewall_inbound = {}
    if "tcp" in inbound:
        firewall_inbound["tcp"] = require_port_list(inbound.get("tcp"), "firewall.inbound.tcp")
    if "udp" in inbound:
        firewall_inbound["udp"] = require_port_list(inbound.get("udp"), "firewall.inbound.udp")

    health = require_allowed_keys(root.get("health"), "health", {"required"}, {"required"})
    required_units = require_string_list(health.get("required"), "health.required")

    container = require_mapping(root.get("container"), "container")
    rendered_units, runtime_units, warnings = render_containers(container, config_root)
    if not rendered_units:
        raise ProvisionError("config.toml must define at least one Quadlet unit")

    for unit in required_units:
        if unit not in container:
            raise ProvisionError(f"health.required references unknown unit: {unit}")

    return {
        "ssh_keys": ssh_keys,
        "firewall_inbound": firewall_inbound,
        "required_units": required_units,
        "rendered_units": rendered_units,
        "runtime": {
            "app_user": APP_RUNTIME_USER,
            "rootless_network": ROOTLESS_NETWORK_NAME,
            "units": runtime_units,
        },
        "warnings": warnings,
    }


def detect_bundle_kind(source_bytes: bytes, filename: str = ""):
    lowered = filename.lower()
    if lowered.endswith((".tar.gz", ".tgz")) or source_bytes.startswith(GZIP_MAGIC):
        return "tar.gz"
    if lowered.endswith((".tar.zst", ".tzst")) or source_bytes.startswith(ZSTD_MAGIC):
        return "tar.zst"
    return None


def validate_bundle_member(name: str):
    path = Path(name)
    if path.is_absolute() or ".." in path.parts or name in {"", "."}:
        raise ProvisionError(f"invalid bundle member path: {name!r}")


def extract_bundle_archive(source_bytes: bytes, filename: str, destination: Path):
    bundle_kind = detect_bundle_kind(source_bytes, filename)
    if bundle_kind == "tar.gz":
        try:
            decompressed = subprocess.run(
                ["gzip", "-dc"],
                input=source_bytes,
                capture_output=True,
                check=True,
            ).stdout
        except FileNotFoundError as exc:
            raise ProvisionError("gzip is required to import .tar.gz bundles") from exc
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.decode("utf-8", errors="replace").strip()
            detail = f": {stderr}" if stderr else ""
            raise ProvisionError(f"failed to decompress .tar.gz bundle{detail}") from exc
        archive = tarfile.open(fileobj=io.BytesIO(decompressed), mode="r:")
    elif bundle_kind == "tar.zst":
        try:
            decompressed = subprocess.run(
                ["zstd", "-dcq"],
                input=source_bytes,
                capture_output=True,
                check=True,
            ).stdout
        except FileNotFoundError as exc:
            raise ProvisionError("zstd is required to import .tar.zst bundles") from exc
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.decode("utf-8", errors="replace").strip()
            detail = f": {stderr}" if stderr else ""
            raise ProvisionError(f"failed to decompress .tar.zst bundle{detail}") from exc
        archive = tarfile.open(fileobj=io.BytesIO(decompressed), mode="r:")
    else:
        raise ProvisionError("supported bundle formats are .tar.gz, .tgz, .tar.zst, and .tzst")

    with archive:
        for member in archive.getmembers():
            validate_bundle_member(member.name)
            target = destination / member.name
            if member.isdir():
                ensure_dir(target)
                os.chmod(target, 0o755)
                continue
            if not member.isfile():
                raise ProvisionError(f"unsupported bundle member type: {member.name}")

            ensure_dir(target.parent)
            extracted = archive.extractfile(member)
            if extracted is None:
                raise ProvisionError(f"failed to read bundle member: {member.name}")
            with extracted, target.open("wb") as output:
                shutil.copyfileobj(extracted, output)
            os.chmod(target, 0o644)


def validate_bundle_layout(bundle_root: Path):
    allowed_entries = {"config.toml", "files"}
    actual_entries = {entry.name for entry in bundle_root.iterdir()}
    if "config.toml" not in actual_entries:
        raise ProvisionError("bundle must contain config.toml at the top level")

    unexpected = actual_entries - allowed_entries
    if unexpected:
        names = ", ".join(sorted(unexpected))
        raise ProvisionError(f"bundle contains unsupported top-level entries: {names}")

    files_dir = bundle_root / "files"
    if files_dir.exists() and not files_dir.is_dir():
        raise ProvisionError("bundle entry 'files' must be a directory")


def prepare_bundle_from_bytes(source_bytes: bytes, filename: str = ""):
    tmpdir = tempfile.TemporaryDirectory()
    bundle_root = Path(tmpdir.name)
    extract_bundle_archive(source_bytes, filename, bundle_root)
    validate_bundle_layout(bundle_root)
    return tmpdir, bundle_root / "config.toml", bundle_root / "files"


def prepare_source_path(source_path: Path):
    if source_path.suffix == ".toml":
        return None, source_path, None

    source_bytes = source_path.read_bytes()
    bundle_kind = detect_bundle_kind(source_bytes, source_path.name)
    if bundle_kind is None:
        raise ProvisionError("supported import inputs are config.toml, .tar.gz/.tgz, and .tar.zst/.tzst")
    return prepare_bundle_from_bytes(source_bytes, source_path.name)


def prepare_source_bytes(source_bytes: bytes, filename: str = ""):
    bundle_kind = detect_bundle_kind(source_bytes, filename)
    if bundle_kind is not None:
        return prepare_bundle_from_bytes(source_bytes, filename)

    tmpdir = tempfile.TemporaryDirectory()
    config_path = Path(tmpdir.name) / "config.toml"
    config_path.write_bytes(source_bytes)
    return tmpdir, config_path, None


def copy_bundle_files(files_source: Path | None, config_root: Path):
    target = config_root / "files"
    shutil.rmtree(target, ignore_errors=True)
    if files_source is None or not files_source.exists():
        return

    for source in files_source.rglob("*"):
        relative = source.relative_to(files_source)
        destination = target / relative
        if source.is_dir():
            ensure_dir(destination)
            os.chmod(destination, 0o755)
            continue

        ensure_dir(destination.parent)
        shutil.copyfile(source, destination)
        os.chmod(destination, 0o644)


def write_imported_state(parsed: dict, prepared_config: Path, prepared_files: Path | None, config_root: Path):
    ensure_dir(config_root)
    ensure_dir(config_root / "ssh-authorized-keys")
    ensure_dir(config_root / "quadlet")

    imported_path = config_root / "config.toml"
    shutil.copyfile(prepared_config, imported_path)
    os.chmod(imported_path, 0o600)

    ssh_path = config_root / "ssh-authorized-keys" / "admin"
    ssh_path.write_text("\n".join(parsed["ssh_keys"]) + "\n")
    os.chmod(ssh_path, 0o600)
    maybe_chown_user(ssh_path, "admin")

    health_path = config_root / "health-required.json"
    health_path.write_text(json.dumps(parsed["required_units"], indent=2) + "\n")
    os.chmod(health_path, 0o600)

    firewall_path = config_root / FIREWALL_INBOUND_FILENAME
    firewall_path.write_text(json.dumps(parsed["firewall_inbound"], indent=2) + "\n")
    os.chmod(firewall_path, 0o600)

    runtime_path = config_root / RUNTIME_METADATA_FILENAME
    runtime_path.write_text(json.dumps(parsed["runtime"], indent=2) + "\n")
    os.chmod(runtime_path, 0o600)

    quadlet_dir = config_root / "quadlet"
    for existing in quadlet_dir.iterdir():
        if existing.is_file():
            existing.unlink()
    for filename, content in parsed["rendered_units"].items():
        unit_path = quadlet_dir / filename
        unit_path.write_text(content)
        os.chmod(unit_path, 0o644)

    copy_bundle_files(prepared_files, config_root)


def load_runtime_metadata(config_root: Path):
    metadata_path = config_root / RUNTIME_METADATA_FILENAME
    if not metadata_path.exists():
        raise ProvisionError(f"missing runtime metadata: {metadata_path}")

    try:
        metadata = json.loads(metadata_path.read_text())
    except json.JSONDecodeError as exc:
        raise ProvisionError(f"invalid runtime metadata in {metadata_path}: {exc}") from exc

    if not isinstance(metadata, dict) or not isinstance(metadata.get("units"), list):
        raise ProvisionError(f"invalid runtime metadata structure in {metadata_path}")
    return metadata


def import_config(config_path: Path, config_root: Path):
    temp_bundle, prepared_config, prepared_files = prepare_source_path(config_path)
    try:
        parsed = load_config(prepared_config, config_root)
        write_imported_state(parsed, prepared_config, prepared_files, config_root)
        return parsed["warnings"]
    finally:
        if temp_bundle is not None:
            temp_bundle.cleanup()


def validate_config_source(source_path: Path):
    temp_bundle, prepared_config, _prepared_files = prepare_source_path(source_path)
    try:
        parsed = load_config(prepared_config)
        return parsed["warnings"]
    finally:
        if temp_bundle is not None:
            temp_bundle.cleanup()


def sync_quadlet_units(config_root: Path, rootful_target: Path, rootless_target: Path | None = None):
    source = config_root / "quadlet"
    metadata = load_runtime_metadata(config_root)
    units_by_mode = {"rootful": set(), "rootless": set()}
    for unit in metadata["units"]:
        if not isinstance(unit, dict):
            raise ProvisionError("invalid runtime unit entry")
        filename = unit.get("filename")
        mode = unit.get("mode")
        if not isinstance(filename, str) or mode not in units_by_mode:
            raise ProvisionError("invalid runtime unit metadata")
        units_by_mode[mode].add(filename)

    ensure_dir(rootful_target)
    existing_rootful = {
        path.name for path in rootful_target.iterdir() if path.is_file() and path.suffix in QUADLET_SUFFIXES
    }
    desired_rootful = units_by_mode["rootful"]

    for filename in desired_rootful:
        unit_file = source / filename
        shutil.copyfile(unit_file, rootful_target / filename)
        os.chmod(rootful_target / filename, 0o644)

    for stale in existing_rootful - desired_rootful:
        (rootful_target / stale).unlink()

    if rootless_target is None:
        if units_by_mode["rootless"]:
            raise ProvisionError("rootless target path is required when rootless units are present")
        return

    ensure_dir(rootless_target)
    existing_rootless = {
        path.name for path in rootless_target.iterdir() if path.is_file() and path.suffix in QUADLET_SUFFIXES
    }
    desired_rootless = units_by_mode["rootless"]

    for filename in desired_rootless:
        unit_file = source / filename
        shutil.copyfile(unit_file, rootless_target / filename)
        os.chmod(rootless_target / filename, 0o644)

    for stale in existing_rootless - desired_rootless:
        (rootless_target / stale).unlink()


BOOTSTRAP_HTML = """<!doctype html>
<html>
  <head>
    <meta charset=\"utf-8\">
    <title>AtomixOS Bootstrap</title>
    <style>
      body {{ font-family: sans-serif; max-width: 48rem; margin: 2rem auto; padding: 0 1rem; }}
      textarea {{ width: 100%; min-height: 18rem; font-family: monospace; }}
      label {{ display: block; margin-top: 1rem; }}
      button {{ margin-top: 1rem; padding: 0.5rem 1rem; }}
      .note {{ color: #444; }}
    </style>
  </head>
  <body>
    <h1>AtomixOS Bootstrap</h1>
    <p class=\"note\">Upload an existing <code>config.toml</code>, <code>config.tar.gz</code>, or <code>config.tar.zst</code> bundle as a file or paste a plain <code>config.toml</code> below, or fill the basic form to generate one.</p>
    <form method=\"post\" action=\"/apply\" enctype=\"multipart/form-data\">
      <label>Config file or bundle</label>
      <input type=\"file\" name=\"config_file\" accept=\".toml,.tar.gz,.tgz,.tar.zst,.tzst,text/plain,application/gzip,application/zstd,application/octet-stream\">
      <label>config.toml</label>
      <textarea name=\"config\">{config_text}</textarea>
      <button type=\"submit\">Apply configuration</button>
    </form>
    <hr>
    <form method=\"post\" action=\"/generate\">
      <label>Admin SSH keys (one per line)</label>
      <textarea name=\"ssh_keys\" style=\"min-height:8rem\"></textarea>
      <label>WAN TCP ports (one per line)</label>
      <textarea name=\"wan_tcp\" style=\"min-height:6rem\">443</textarea>
      <label>WAN UDP ports (one per line)</label>
      <textarea name=\"wan_udp\" style=\"min-height:6rem\">1194</textarea>
      <label>Required health units (one per line)</label>
      <textarea name=\"required\" style=\"min-height:6rem\"></textarea>
      <label>Container TOML snippet</label>
      <textarea name=\"quadlet\">[container.myapp]\nprivileged = false\n\n[container.myapp.Unit]\nDescription = \"My App\"\n\n[container.myapp.Container]\nImage = \"ghcr.io/example/myapp:latest\"\nPublishPort = [\"10080:8080\"]\n\n[container.myapp.Install]\nWantedBy = [\"default.target\"]\n</textarea>
      <button type=\"submit\">Generate config.toml</button>
    </form>
    {message}
  </body>
</html>
"""


class BootstrapHandler(BaseHTTPRequestHandler):
    config_root = None
    output_path = None

    def _mark_applied(self):
        output_path = getattr(self, "output_path", None)
        if not output_path:
            return
        Path(output_path).write_text("applied\n")

    def _write_payload(self, payload: bytes, filename: str = "config.toml"):
        temp_bundle, prepared_config, prepared_files = prepare_source_bytes(payload, filename)
        try:
            parsed = load_config(prepared_config, Path(self.config_root))
            write_imported_state(parsed, prepared_config, prepared_files, Path(self.config_root))
        finally:
            temp_bundle.cleanup()

    def _read_multipart_form(self, body: bytes):
        content_type = self.headers.get("Content-Type", "")
        message = BytesParser(policy=email.policy.default).parsebytes(
            f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode() + body
        )
        form = {}
        for part in message.iter_parts():
            name = part.get_param("name", header="Content-Disposition")
            if not name:
                continue
            payload = part.get_payload(decode=True) or b""
            filename = part.get_param("filename", header="Content-Disposition")
            if filename:
                form[name] = {
                    "filename": Path(filename).name,
                    "body": payload,
                }
                continue
            charset = part.get_content_charset("utf-8") or "utf-8"
            form[name] = payload.decode(charset)
        return form

    def _read_form(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        content_type = self.headers.get("Content-Type", "")
        if content_type.startswith("multipart/form-data"):
            return self._read_multipart_form(body)
        return {k: v[-1] for k, v in parse_qs(body.decode(), keep_blank_values=True).items()}

    def _send_html(self, config_text="", message=""):
        body = BOOTSTRAP_HTML.format(config_text=html.escape(config_text), message=message)
        body_bytes = body.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body_bytes)))
        self.end_headers()
        self.wfile.write(body_bytes)

    def _send_json(self, status: int, payload: dict):
        body_bytes = (json.dumps(payload) + "\n").encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body_bytes)))
        self.end_headers()
        self.wfile.write(body_bytes)

    def do_GET(self):
        self._send_html()

    def do_POST(self):
        if self.path == "/api/config":
            length = int(self.headers.get("Content-Length", "0"))
            payload = self.rfile.read(length)
            filename = self.headers.get("X-Config-Filename", "config.toml")
            try:
                self._write_payload(payload, filename)
            except Exception as exc:  # noqa: BLE001
                self._send_json(400, {"ok": False, "error": str(exc)})
                return

            self._send_json(200, {"ok": True, "message": "Configuration applied."})
            self._mark_applied()
            return

        form = self._read_form()
        if self.path == "/apply":
            uploaded = form.get("config_file")
            if isinstance(uploaded, dict) and uploaded.get("body"):
                payload = uploaded["body"]
                filename = uploaded.get("filename", "config.toml")
                config_text = ""
            else:
                config_text = form.get("config", "")
                payload = config_text.encode("utf-8")
                filename = "config.toml"
        elif self.path == "/generate":
            ssh_keys = [line.strip() for line in form.get("ssh_keys", "").splitlines() if line.strip()]
            tcp_ports = [int(line.strip()) for line in form.get("wan_tcp", "").splitlines() if line.strip()]
            udp_ports = [int(line.strip()) for line in form.get("wan_udp", "").splitlines() if line.strip()]
            required = [line.strip() for line in form.get("required", "").splitlines() if line.strip()]
            quadlet = form.get("quadlet", "").strip()
            firewall_lines = ["[firewall.inbound]"]
            if tcp_ports:
                firewall_lines.append(f"tcp = {json.dumps(tcp_ports)}")
            if udp_ports:
                firewall_lines.append(f"udp = {json.dumps(udp_ports)}")
            firewall_text = "\n".join(firewall_lines)
            config_text = textwrap.dedent(
                f"""
                version = 1

                [admin]
                ssh_keys = {json.dumps(ssh_keys)}

                {firewall_text}

                [health]
                required = {json.dumps(required)}

                {quadlet}
                """
            ).strip() + "\n"
            payload = config_text.encode("utf-8")
            filename = "config.toml"
        else:
            self.send_error(404)
            return

        try:
            self._write_payload(payload, filename)
        except Exception as exc:  # noqa: BLE001
            self._send_html(config_text=config_text, message=f"<p><strong>Error:</strong> {html.escape(str(exc))}</p>")
            return

        self._send_html(config_text=config_text, message="<p><strong>Configuration applied.</strong></p>")
        self._mark_applied()

    def log_message(self, format, *args):
        sys.stderr.write("[bootstrap] " + (format % args) + "\n")


def serve_bootstrap(config_root: Path, output_path: Path, host: str, port: int):
    BootstrapHandler.config_root = str(config_root)
    BootstrapHandler.output_path = str(output_path)
    httpd = ThreadingHTTPServer((host, port), BootstrapHandler)
    httpd.serve_forever()


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    validate_parser = sub.add_parser("validate")
    validate_parser.add_argument("config")

    import_parser = sub.add_parser("import")
    import_parser.add_argument("config")
    import_parser.add_argument("config_root")

    sync_parser = sub.add_parser("sync-quadlet")
    sync_parser.add_argument("config_root")
    sync_parser.add_argument("target_root")
    sync_parser.add_argument("rootless_target", nargs="?")

    serve_parser = sub.add_parser("serve")
    serve_parser.add_argument("config_root")
    serve_parser.add_argument("output")
    serve_parser.add_argument("--host", default="0.0.0.0")
    serve_parser.add_argument("--port", type=int, default=8080)

    args = parser.parse_args()

    try:
        if args.command == "validate":
            for warning in validate_config_source(Path(args.config)):
                print(f"warning: {warning}", file=sys.stderr)
        elif args.command == "import":
            for warning in import_config(Path(args.config), Path(args.config_root)):
                print(f"warning: {warning}", file=sys.stderr)
        elif args.command == "sync-quadlet":
            sync_quadlet_units(
                Path(args.config_root),
                Path(args.target_root),
                Path(args.rootless_target) if args.rootless_target else None,
            )
        elif args.command == "serve":
            serve_bootstrap(Path(args.config_root), Path(args.output), args.host, args.port)
    except ProvisionError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

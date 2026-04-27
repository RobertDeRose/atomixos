#!/usr/bin/env python3
import argparse
import email.policy
import html
import io
import json
import os
import shutil
import stat
import sys
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


SUPPORTED_TYPES = {"container", "network", "volume", "pod", "build", "image"}
REPEATED_KEYS = {
    "AddCapability",
    "Annotation",
    "DNS",
    "DNSOption",
    "DNSSearch",
    "DropCapability",
    "Environment",
    "EnvironmentFile",
    "Exec",
    "GlobalArgs",
    "GroupAdd",
    "Label",
    "Mount",
    "Network",
    "PodmanArgs",
    "PublishPort",
    "Secret",
    "Tmpfs",
    "Volume",
    "WantedBy",
  }

TYPE_TO_SUFFIX = {
    "container": ".container",
    "network": ".network",
    "volume": ".volume",
    "pod": ".pod",
    "build": ".build",
    "image": ".image",
}


class ProvisionError(RuntimeError):
    pass


def validate_name(name: str) -> str:
    if not name or "/" in name or "\x00" in name or name in {".", ".."}:
        raise ProvisionError(f"invalid quadlet unit name: {name!r}")
    return name


def require_mapping(value, path: str):
    if not isinstance(value, dict):
        raise ProvisionError(f"expected table at {path}")
    return value


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


def ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)


def format_scalar(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return value
    raise ProvisionError(f"unsupported scalar value type: {type(value).__name__}")


def render_quadlet(quadlet_table: dict):
    rendered = {}
    for quadlet_type, units in quadlet_table.items():
        if quadlet_type not in SUPPORTED_TYPES:
            raise ProvisionError(f"unsupported quadlet type: {quadlet_type}")
        unit_table = require_mapping(units, f"quadlet.{quadlet_type}")
        for unit_name, sections in unit_table.items():
            validate_name(unit_name)
            section_table = require_mapping(sections, f"quadlet.{quadlet_type}.{unit_name}")
            lines = []
            for section_name, directives in section_table.items():
                directives_table = require_mapping(
                    directives,
                    f"quadlet.{quadlet_type}.{unit_name}.{section_name}",
                )
                lines.append(f"[{section_name}]")
                for key, raw_value in directives_table.items():
                    if isinstance(raw_value, list):
                        if not raw_value:
                            continue
                        for item in raw_value:
                            lines.append(f"{key}={format_scalar(item)}")
                    else:
                        lines.append(f"{key}={format_scalar(raw_value)}")
                lines.append("")
            rendered[f"{unit_name}{TYPE_TO_SUFFIX[quadlet_type]}"] = "\n".join(lines).rstrip() + "\n"
    return rendered


def load_config(config_path: Path):
    try:
        data = tomllib.loads(config_path.read_text())
    except tomllib.TOMLDecodeError as exc:
        raise ProvisionError(f"invalid TOML in {config_path}: {exc}") from exc

    admin = require_mapping(data.get("admin"), "admin")
    password_hash = require_string(admin.get("password_hash"), "admin.password_hash")
    ssh_keys = require_string_list(admin.get("ssh_keys"), "admin.ssh_keys")

    health = require_mapping(data.get("health"), "health")
    required_units = require_string_list(health.get("required"), "health.required")

    quadlet = require_mapping(data.get("quadlet"), "quadlet")
    rendered_units = render_quadlet(quadlet)
    if not rendered_units:
        raise ProvisionError("config.toml must define at least one Quadlet unit")

    for unit in required_units:
        known = f"{unit}.container" in rendered_units or f"{unit}.pod" in rendered_units
        if not known:
            raise ProvisionError(f"health.required references unknown unit: {unit}")

    return {
        "password_hash": password_hash,
        "ssh_keys": ssh_keys,
        "required_units": required_units,
        "rendered_units": rendered_units,
    }


def import_config(config_path: Path, config_root: Path):
    parsed = load_config(config_path)

    ensure_dir(config_root)
    ensure_dir(config_root / "ssh-authorized-keys")
    ensure_dir(config_root / "quadlet")

    imported_path = config_root / "config.toml"
    shutil.copyfile(config_path, imported_path)
    os.chmod(imported_path, 0o600)

    password_path = config_root / "admin-password-hash"
    password_path.write_text(parsed["password_hash"] + "\n")
    os.chmod(password_path, 0o600)

    ssh_path = config_root / "ssh-authorized-keys" / "admin"
    ssh_path.write_text("\n".join(parsed["ssh_keys"]) + "\n")
    os.chmod(ssh_path, 0o600)

    health_path = config_root / "health-required.json"
    health_path.write_text(json.dumps(parsed["required_units"], indent=2) + "\n")
    os.chmod(health_path, 0o600)

    quadlet_dir = config_root / "quadlet"
    for existing in quadlet_dir.iterdir():
        if existing.is_file():
            existing.unlink()
    for filename, content in parsed["rendered_units"].items():
        unit_path = quadlet_dir / filename
        unit_path.write_text(content)
        os.chmod(unit_path, 0o644)


def sync_quadlet_units(config_root: Path, target_root: Path):
    source = config_root / "quadlet"
    ensure_dir(target_root)

    existing_targets = {
        path.name for path in target_root.iterdir() if path.is_file() and path.suffix in TYPE_TO_SUFFIX.values()
    }
    desired = set()

    if source.exists():
        for unit_file in source.iterdir():
            if not unit_file.is_file():
                continue
            desired.add(unit_file.name)
            shutil.copyfile(unit_file, target_root / unit_file.name)
            os.chmod(target_root / unit_file.name, 0o644)

    for stale in existing_targets - desired:
        (target_root / stale).unlink()


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
    <p class=\"note\">Upload an existing <code>config.toml</code> as a file or paste it below, or fill the basic form to generate one.</p>
    <form method=\"post\" action=\"/apply\" enctype=\"multipart/form-data\">
      <label>config.toml file</label>
      <input type=\"file\" name=\"config_file\" accept=\".toml,text/plain\">
      <label>config.toml</label>
      <textarea name=\"config\">{config_text}</textarea>
      <button type=\"submit\">Apply config.toml</button>
    </form>
    <hr>
    <form method=\"post\" action=\"/generate\">
      <label>Admin password hash</label>
      <textarea name=\"password_hash\" style=\"min-height:4rem\"></textarea>
      <label>Admin SSH keys (one per line)</label>
      <textarea name=\"ssh_keys\" style=\"min-height:8rem\"></textarea>
      <label>Required health units (one per line)</label>
      <textarea name=\"required\" style=\"min-height:6rem\"></textarea>
      <label>Quadlet TOML snippet</label>
      <textarea name=\"quadlet\">[quadlet.container.myapp.Unit]\nDescription = \"My App\"\n\n[quadlet.container.myapp.Container]\nImage = \"ghcr.io/example/myapp:latest\"\n\n[quadlet.container.myapp.Install]\nWantedBy = [\"multi-user.target\"]\n</textarea>
      <button type=\"submit\">Generate config.toml</button>
    </form>
    {message}
  </body>
</html>
"""


class BootstrapHandler(BaseHTTPRequestHandler):
    config_root = None
    output_path = None

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

    def do_GET(self):
        self._send_html()

    def do_POST(self):
        form = self._read_form()
        if self.path == "/apply":
            config_text = form.get("config_file", "") or form.get("config", "")
        elif self.path == "/generate":
            ssh_keys = [line.strip() for line in form.get("ssh_keys", "").splitlines() if line.strip()]
            required = [line.strip() for line in form.get("required", "").splitlines() if line.strip()]
            quadlet = form.get("quadlet", "").strip()
            config_text = textwrap.dedent(
                f"""
                [admin]
                password_hash = {json.dumps(form.get('password_hash', '').strip())}
                ssh_keys = {json.dumps(ssh_keys)}

                [health]
                required = {json.dumps(required)}

                {quadlet}
                """
            ).strip() + "\n"
        else:
            self.send_error(404)
            return

        try:
            temp_path = Path(self.output_path)
            temp_path.write_text(config_text)
            import_config(temp_path, Path(self.config_root))
        except Exception as exc:  # noqa: BLE001
            self._send_html(config_text=config_text, message=f"<p><strong>Error:</strong> {html.escape(str(exc))}</p>")
            return

        self._send_html(config_text=config_text, message="<p><strong>Configuration applied.</strong> You can now close this page and continue boot.</p>")

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

    serve_parser = sub.add_parser("serve")
    serve_parser.add_argument("config_root")
    serve_parser.add_argument("output")
    serve_parser.add_argument("--host", default="0.0.0.0")
    serve_parser.add_argument("--port", type=int, default=8080)

    args = parser.parse_args()

    try:
        if args.command == "validate":
            load_config(Path(args.config))
        elif args.command == "import":
            import_config(Path(args.config), Path(args.config_root))
        elif args.command == "sync-quadlet":
            sync_quadlet_units(Path(args.config_root), Path(args.target_root))
        elif args.command == "serve":
            serve_bootstrap(Path(args.config_root), Path(args.output), args.host, args.port)
    except ProvisionError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

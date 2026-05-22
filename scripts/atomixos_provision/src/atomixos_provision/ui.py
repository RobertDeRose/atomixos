"""Boot UI HTML routes (/, /apply, /assets/atomixos.png) — Litestar handlers.

The Boot UI is only available before initial provisioning. Once the device
is provisioned (admin signers exist), all UI routes return 404.
"""

# ruff: noqa: E501

import asyncio
import html
import secrets
from pathlib import Path
from typing import Any

from litestar import Request, get, post
from litestar.datastructures import State
from litestar.exceptions import NotFoundException
from litestar.response import Response

from atomixos_provision.bootstrap_security import enforce_bootstrap_browser_origin
from atomixos_provision.config import ProvisionError
from atomixos_provision.jobs import JobManager

__all__ = ["ui_routes"]


DEFAULT_QUADLET_SNIPPET = """[container.myapp]
privileged = false

[container.myapp.Unit]
Description = "My App"

[container.myapp.Container]
Image = "ghcr.io/example/myapp:latest"
PublishPort = ["10080:8080"]

[container.myapp.Install]
WantedBy = ["default.target"]
"""


def render_bootstrap_page(
    config_text: str = "", message_html: str = "", bootstrap_token: str = ""
) -> str:
    message_block = f'<section class="message">{message_html}</section>' if message_html else ""
    return f"""<!doctype html>
<html>
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>AtomixOS Bootstrap</title>
    <style>
      :root {{ color-scheme: dark; --bg: #06102a; --panel: rgba(11, 26, 58, 0.88); --fg: #d4e6ff; --muted: #c3dbff; --accent: #4ea3ff; }}
      * {{ box-sizing: border-box; }}
      body {{ margin: 0; font-family: Inter, ui-sans-serif, system-ui, sans-serif; color: var(--fg); background: radial-gradient(circle at 16% 8%, rgba(76,146,255,.2), transparent 36%), var(--bg); }}
      main {{ max-width: 60rem; margin: 0 auto; padding: 1.5rem 1rem 2rem; }}
      .hero {{ text-align: center; margin-bottom: 1.5rem; }}
      .hero-mark {{ width: min(19rem, 68vw); height: auto; }}
      .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(18rem, 1fr)); gap: 1rem; }}
      .panel, .message {{ background: var(--panel); border: 1px solid rgba(93,121,168,.34); border-radius: 14px; padding: 1rem; }}
      label {{ display: block; margin-top: .9rem; margin-bottom: .35rem; font-weight: 600; }}
      input[type=file], input[type=text], textarea {{ width: 100%; border-radius: 10px; border: 1px solid rgba(124,183,255,.28); background: rgba(10,22,50,.9); color: var(--fg); padding: .8rem .9rem; font: inherit; }}
      textarea {{ min-height: 18rem; resize: vertical; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }}
      .short {{ min-height: 6rem; }} .medium {{ min-height: 8rem; }}
      button {{ margin-top: 1rem; border: 0; border-radius: 999px; background: var(--accent); color: #f4f9ff; cursor: pointer; font: inherit; font-weight: 700; padding: .75rem 1.15rem; }}
      code {{ color: #c6defe; }}
    </style>
    <script>
      function downloadAppliedConfig() {{
        const textarea = document.querySelector('textarea[name="config"]');
        if (!textarea) return;
        const blob = new Blob([textarea.value], {{ type: 'text/plain;charset=utf-8' }});
        const href = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = href; link.download = 'config.toml'; document.body.appendChild(link);
        link.click(); link.remove(); URL.revokeObjectURL(href);
      }}
      function bytesToHex(bytes) {{
        return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
      }}
      function bytesToBase64(bytes) {{
        let binary = '';
        bytes.forEach((b) => binary += String.fromCharCode(b));
        return btoa(binary);
      }}
      async function prepareApplyChallenge() {{
        const form = document.querySelector('form[action="/apply"]');
        const fileInput = form.querySelector('input[name="config_file"]');
        const textInput = form.querySelector('textarea[name="config"]');
        const encoder = new TextEncoder();
        const payload = fileInput.files.length ? await fileInput.files[0].arrayBuffer() : encoder.encode(textInput.value).buffer;
        const nonceResponse = await fetch('/api/nonce');
        if (!nonceResponse.ok) throw new Error('failed to fetch nonce');
        const nonce = (await nonceResponse.json()).nonce;
        const hash = await crypto.subtle.digest('SHA-256', payload);
        const challenge = `atomixos-reapply-v1\nnonce:${{nonce}}\npath:/apply\nsha256:${{bytesToHex(new Uint8Array(hash))}}\n`;
        form.querySelector('input[name="auth_nonce"]').value = nonce;
        form.querySelector('textarea[name="auth_challenge"]').value = challenge;
        form.querySelector('textarea[name="auth_signature"]').value = '';
        const blob = new Blob([challenge], {{ type: 'text/plain;charset=utf-8' }});
        const href = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = href; link.download = 'atomixos-reapply-challenge.txt'; document.body.appendChild(link);
        link.click(); link.remove(); URL.revokeObjectURL(href);
      }}
      function normalizeSignature(event) {{
        const file = event.target.files[0];
        if (!file) return;
        file.arrayBuffer().then((buffer) => {{
          const bytes = new Uint8Array(buffer);
          event.target.form.querySelector('textarea[name="auth_signature"]').value = bytesToBase64(bytes);
        }});
      }}
    </script>
  </head>
  <body>
    <main>
      <section class="hero">
        <img class="hero-mark" src="/assets/atomixos.png" alt="AtomixOS logo">
        <h1>Bootstrap Console</h1>
        <p>Import an existing <code>config.toml</code> or supported config bundle.</p>
      </section>
      <section class="grid">
        <form class="panel" method="post" action="/apply" enctype="multipart/form-data">
          <h2>Apply Existing Configuration</h2>
          <p>Upload a prepared config or paste a plain <code>config.toml</code> payload.</p>
          <input type="hidden" name="bootstrap_token" value="{html.escape(bootstrap_token)}">
          <label>Config file or bundle</label><input type="file" name="config_file">
          <label>config.toml</label><textarea name="config">{html.escape(config_text)}</textarea>
          <button type="submit">Apply configuration</button>
        </form>
      </section>
      {message_block}
    </main>
  </body>
</html>"""


def uploaded_config_text(payload: bytes, filename: str) -> str:
    lowered = filename.lower()
    if lowered.endswith((".toml", ".txt")):
        return payload.decode("utf-8", errors="replace")
    return ""


async def _require_unprovisioned(connection, _: Any) -> None:
    """Guard that rejects requests once the device is provisioned."""
    config_root: Path = connection.app.state.config_root
    if (config_root / "config.toml").exists() or (config_root / "admin-signers").exists():
        raise NotFoundException()


@get("/", guards=[_require_unprovisioned], include_in_schema=False)
async def boot_ui(request: Request, state: State) -> Response[str]:
    """GET / — serve the Boot UI HTML page."""
    enforce_bootstrap_browser_origin(request)
    return Response(
        render_bootstrap_page(bootstrap_token=state.bootstrap_token),
        media_type="text/html",
    )


@get("/assets/atomixos.png", include_in_schema=False)
async def serve_logo(state: State) -> Response[Any]:
    """GET /assets/atomixos.png — serve the static logo."""
    logo: Path | None = state.get("logo_path")
    if logo and logo.exists():
        content = await asyncio.to_thread(logo.read_bytes)
        return Response(content=content, media_type="image/png")
    return Response(content=b"", status_code=404)


@post("/apply", guards=[_require_unprovisioned], include_in_schema=False)
async def apply_form(request: Request, state: State) -> Response[str]:
    """POST /apply — multipart form upload -> sync provision -> HTML result."""
    from atomixos_provision.provision import apply_config_bytes

    config_root: Path = state.config_root
    job_manager: JobManager = state.job_manager
    enforce_bootstrap_browser_origin(request)
    form = await request.form()
    bootstrap_token = str(form.get("bootstrap_token", ""))
    if not secrets.compare_digest(bootstrap_token, state.bootstrap_token):
        return Response(
            "<html><body><h1>Error</h1><p>Invalid bootstrap token.</p></body></html>",
            status_code=403,
            media_type="text/html",
        )

    config_file = form.get("config_file")
    if config_file is None:
        config_text = form.get("config", "")
        if not config_text:
            return Response(
                "<html><body><h1>Error</h1><p>No config provided.</p></body></html>",
                status_code=400,
                media_type="text/html",
            )
        payload = config_text.encode("utf-8") if isinstance(config_text, str) else config_text
        filename = "config.toml"
    else:
        payload = await config_file.read()
        filename = getattr(config_file, "filename", "config.toml") or "config.toml"
        config_text = uploaded_config_text(payload, filename)

    try:

        async def provision_work(job):
            return await apply_config_bytes(
                payload, filename, config_root, job, allow_reapply=False
            )

        result = await job_manager.run_sync(provision_work)
        if result is None:
            return Response(
                "<html><body><h1>Error</h1>"
                "<p>A provision job is already running.</p></body></html>",
                status_code=409,
                media_type="text/html",
            )
        warnings = result.get("warnings", [])
        warning_html = "".join(f"<li>{html.escape(w)}</li>" for w in warnings)
        message = (
            "<p><strong>Configuration applied.</strong> Use the button below to save "
            "the rendered <code>config.toml</code> directly from this page.</p>"
            '<div class="message-actions"><button type="button" '
            'onclick="downloadAppliedConfig()">Download applied config.toml</button></div>'
            f"{'<h2>Warnings</h2><ul>' + warning_html + '</ul>' if warnings else ''}"
        )
        return Response(
            render_bootstrap_page(config_text=config_text, message_html=message),
            status_code=201,
            media_type="text/html",
        )
    except ProvisionError as exc:
        rollback = getattr(exc, "rollback_status", None)
        rollback_html = (
            f"<p><strong>Rollback status:</strong> {html.escape(rollback)}</p>" if rollback else ""
        )
        return Response(
            f"<html><body><h1>Error</h1><p>{html.escape(str(exc))}</p>"
            f"{rollback_html}</body></html>",
            status_code=400,
            media_type="text/html",
        )
    except Exception as exc:
        return Response(
            f"<html><body><h1>Error</h1><p>{html.escape(str(exc))}</p></body></html>",
            status_code=500,
            media_type="text/html",
        )


def ui_routes() -> list:
    """Return the Boot UI route handlers for inclusion in the Litestar app."""
    return [boot_ui, serve_logo, apply_form]

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
from atomixos_provision.jobs import Job, JobManager

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

_BOOT_UI_JOB_IDS = "boot_ui_job_ids"


def render_bootstrap_page(
    config_text: str = "", message_html: str = "", bootstrap_token: str = ""
) -> str:
    message_block = f'<section id="job-status" class="message">{message_html}</section>' if message_html else '<section id="job-status"></section>'
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
      .events {{ margin: .75rem 0 0; padding-left: 1.15rem; }}
      .status-failed {{ border-color: rgba(255, 116, 116, .6); }}
      .status-succeeded {{ border-color: rgba(86, 214, 150, .6); }}
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
      async function applyConfig(event) {{
        event.preventDefault();
        const form = event.currentTarget;
        const target = document.querySelector('#job-status');
        target.innerHTML = '<div class="message"><p><strong>Submitting configuration...</strong></p></div>';
        const response = await fetch(form.action, {{ method: 'POST', body: new FormData(form) }});
        const body = await response.text();
        target.outerHTML = body;
      }}
      async function refreshJobStatus(url) {{
        const target = document.querySelector('#job-status[data-poll="true"]');
        if (!target) return;
        const response = await fetch(url);
        const body = await response.text();
        target.outerHTML = body;
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
        <form class="panel" method="post" action="/apply" enctype="multipart/form-data" onsubmit="applyConfig(event)">
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


def _html_page_fragment(content: str, status_class: str = "") -> str:
    classes = "message" + (f" {status_class}" if status_class else "")
    return f'<section id="job-status" class="{classes}">{content}</section>'


def render_job_fragment(job: Job) -> str:
    snapshot = job.snapshot()
    state = str(snapshot["state"])
    stage = html.escape(str(snapshot["stage"]))
    events = snapshot["events"][-6:]
    event_items = "".join(
        "<li>"
        f"<code>{html.escape(str(event['step']))}</code>"
        f"{': ' + html.escape(str(event.get('message', ''))) if event.get('message') else ''}"
        "</li>"
        for event in events
    )
    event_html = f'<ol class="events">{event_items}</ol>' if event_items else ""

    if state in {"submitted", "running"}:
        fragment = _html_page_fragment(
            f"<p><strong>Applying configuration...</strong></p>"
            f"<p>Current stage: <code>{stage}</code></p>"
            f"{event_html}"
            f'<script>setTimeout(() => refreshJobStatus("/ui/jobs/{html.escape(job.id)}"), 1200);</script>'
        )
        return fragment.replace(
            'id="job-status"', 'id="job-status" data-poll="true"', 1
        )

    if state == "succeeded":
        result = snapshot["result"]
        warnings = result.get("warnings", []) if isinstance(result, dict) else []
        forwarding_url = result.get("forwarding_url") if isinstance(result, dict) else None
        warning_html = "".join(f"<li>{html.escape(str(w))}</li>" for w in warnings)
        forwarding_html = (
            f'<p>Continue at <a href="{html.escape(str(forwarding_url))}">{html.escape(str(forwarding_url))}</a>.</p>'
            if forwarding_url
            else ""
        )
        return _html_page_fragment(
            "<p><strong>Configuration applied.</strong></p>"
            f"{forwarding_html}"
            f"{'<h2>Warnings</h2><ul>' + warning_html + '</ul>' if warnings else ''}",
            "status-succeeded",
        )

    rollback = snapshot.get("rollback_status")
    rollback_html = (
        f"<p><strong>Rollback status:</strong> {html.escape(str(rollback))}</p>" if rollback else ""
    )
    return _html_page_fragment(
        f"<p><strong>Configuration failed.</strong></p>"
        f"<p>{html.escape(str(snapshot.get('error') or 'unknown error'))}</p>"
        f"{rollback_html}"
        f"{event_html}",
        "status-failed",
    )


async def _require_unprovisioned(connection, _: Any) -> None:
    """Guard that rejects requests once the device is provisioned."""
    config_root: Path = connection.app.state.config_root
    if (config_root / "config.toml").exists() or (config_root / "admin-signers").exists():
        raise NotFoundException()


async def _require_unprovisioned_or_boot_ui_terminal_job(connection, _: Any) -> None:
    config_root: Path = connection.app.state.config_root
    if not (config_root / "config.toml").exists() and not (
        config_root / "admin-signers"
    ).exists():
        return

    job_id = str(connection.path_params.get("job_id", ""))
    if not job_id or job_id not in connection.app.state.get(_BOOT_UI_JOB_IDS, set()):
        raise NotFoundException()

    job_manager: JobManager = connection.app.state.job_manager
    job = job_manager.get(job_id)
    if job is None or str(job.snapshot()["state"]) not in {"succeeded", "failed"}:
        raise NotFoundException()


@get("/", guards=[_require_unprovisioned], include_in_schema=False)
async def boot_ui(request: Request, state: State) -> Response[str]:
    """GET / — serve the Boot UI HTML page."""
    enforce_bootstrap_browser_origin(request)
    return Response(
        render_bootstrap_page(bootstrap_token=state.bootstrap_token),
        media_type="text/html",
    )


@get("/assets/atomixos.png", guards=[_require_unprovisioned], include_in_schema=False)
async def serve_logo(state: State) -> Response[Any]:
    """GET /assets/atomixos.png — serve the static logo."""
    logo: Path | None = state.get("logo_path")
    if logo and logo.exists():
        content = await asyncio.to_thread(logo.read_bytes)
        return Response(content=content, media_type="image/png")
    return Response(content=b"", status_code=404)


@post("/apply", guards=[_require_unprovisioned], include_in_schema=False)
async def apply_form(request: Request, state: State) -> Response[str]:
    """POST /apply — multipart form upload -> async provision job fragment."""
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
    upload_filename = getattr(config_file, "filename", "") if config_file is not None else ""
    if config_file is None or not upload_filename:
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
        filename = upload_filename or "config.toml"
        config_text = uploaded_config_text(payload, filename)

    async def provision_work(job):
        return await apply_config_bytes(payload, filename, config_root, job, allow_reapply=False)

    job = await job_manager.submit(provision_work)
    if job is None:
        return Response(
            _html_page_fragment("<p>A provision job is already running.</p>", "status-failed"),
            status_code=409,
            media_type="text/html",
        )

    state.setdefault(_BOOT_UI_JOB_IDS, set()).add(job.id)

    return Response(render_job_fragment(job), status_code=202, media_type="text/html")


@get(
    "/ui/jobs/{job_id:str}",
    guards=[_require_unprovisioned_or_boot_ui_terminal_job],
    include_in_schema=False,
)
async def job_fragment(job_id: str, job_manager: JobManager, state: State) -> Response[str]:
    """GET /ui/jobs/{id} — render first-boot HTML job status."""
    job = job_manager.get(job_id)
    if job is None:
        return Response(
            _html_page_fragment("<p>Provisioning job not found.</p>", "status-failed"),
            status_code=404,
            media_type="text/html",
        )
    body = render_job_fragment(job)
    if str(job.snapshot()["state"]) in {"succeeded", "failed"}:
        state.get(_BOOT_UI_JOB_IDS, set()).discard(job_id)
    return Response(body, media_type="text/html")


def ui_routes() -> list:
    """Return the Boot UI route handlers for inclusion in the Litestar app."""
    return [boot_ui, serve_logo, apply_form, job_fragment]

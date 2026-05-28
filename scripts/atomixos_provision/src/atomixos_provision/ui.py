"""Boot UI HTML routes (/, /apply, /assets/*) — Litestar handlers.

The Boot UI is only available before initial provisioning. Once the device
is provisioned (admin signers exist), all UI routes return 404.
"""

# ruff: noqa: E501

import asyncio
import html
import secrets
import threading
from pathlib import Path
from typing import Any

from litestar import Request, get, post
from litestar.datastructures import State
from litestar.exceptions import NotFoundException
from litestar.response import Response, ServerSentEvent

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
_BOOT_UI_JOB_LOCK = "boot_ui_job_lock"


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
      .hero {{ text-align: center; margin-bottom: 1rem; }}
      .hero-mark {{ width: min(19rem, 68vw); height: auto; display: block; margin: 0 auto -.9rem; }}
      .hero h1 {{ margin: 0; }}
      .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(18rem, 1fr)); gap: 1rem; }}
      .panel, .message {{ background: var(--panel); border: 1px solid rgba(93,121,168,.34); border-radius: 14px; padding: 1rem; }}
      #job-status {{ margin-top: 1rem; }}
      label {{ display: block; margin-top: .9rem; margin-bottom: .35rem; font-weight: 600; }}
      input[type=file] {{ position: absolute; inline-size: 1px; block-size: 1px; opacity: 0; overflow: hidden; clip-path: inset(50%); }}
      input[type=text], textarea {{ width: 100%; border-radius: 10px; border: 1px solid rgba(124,183,255,.28); background: rgba(10,22,50,.9); color: var(--fg); padding: .8rem .9rem; font: inherit; }}
      .file-actions {{ display: grid; grid-template-columns: max-content auto 1fr; align-items: center; gap: 1rem; }}
      .file-picker {{ display: flex; align-items: center; }}
      .file-trigger {{ display: inline-block; border: 0; border-radius: 999px; background: var(--accent); color: #f4f9ff; cursor: pointer; font: inherit; font-weight: 700; padding: .75rem 1.15rem; }}
      .file-separator {{ color: var(--muted); font-weight: 700; }}
      .apply-row {{ align-items: center; display: flex; gap: 1rem; flex-wrap: wrap; margin-top: 1rem; }}
      .file-name {{ color: var(--fg); display: inline-block; font-weight: 700; }}
      .drop-zone {{ align-items: center; background: rgba(39, 86, 162, .34); border: 1px dashed rgba(124,183,255,.7); border-radius: 10px; color: var(--muted); display: flex; flex-direction: column; justify-content: center; min-height: 11rem; padding: .75rem; }}
      .drop-zone.dragging {{ border-color: var(--accent); background: rgba(78,163,255,.18); color: var(--fg); }}
      .drop-icon {{ border-radius: 8px; display: block; height: min(15rem, 36vw); max-height: 100%; max-width: 100%; object-fit: contain; width: min(15rem, 36vw); }}
      .drop-copy {{ color: var(--fg); font-weight: 700; margin-top: .4rem; }}
      textarea {{ min-height: 18rem; resize: vertical; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }}
      .short {{ min-height: 6rem; }} .medium {{ min-height: 8rem; }}
      button {{ margin-top: 1rem; border: 0; border-radius: 999px; background: var(--accent); color: #f4f9ff; cursor: pointer; font: inherit; font-weight: 700; padding: .75rem 1.15rem; }}
      .apply-row button {{ margin-top: 0; }}
      button:disabled {{ cursor: not-allowed; filter: grayscale(.45); opacity: .5; }}
      button.ready {{ animation: pulse 1.05s ease-in-out infinite; }}
      button.submitting {{ align-items: center; display: inline-flex; gap: .55rem; justify-content: center; }}
      button.submitting::before {{ animation: spin .8s linear infinite; border: 2px solid rgba(244,249,255,.42); border-top-color: #f4f9ff; border-radius: 50%; content: ""; height: 1em; width: 1em; }}
      @keyframes pulse {{ 0%, 100% {{ box-shadow: inset 0 0 .45rem rgba(244,249,255,.22), inset 0 0 1.1rem rgba(78,163,255,.45), 0 0 .45rem rgba(78,163,255,.25); transform: scale(1); }} 50% {{ box-shadow: inset 0 0 .75rem rgba(244,249,255,.38), inset 0 0 1.8rem rgba(78,163,255,.82), 0 0 .8rem rgba(78,163,255,.35); transform: scale(1.012); }} }}
      @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
      .events {{ list-style-position: inside; margin: .75rem 0 0; padding-left: 0; }}
      .event-log {{ max-height: 14rem; overflow-y: auto; }}
      .status-failed {{ border-color: rgba(255, 116, 116, .6); }}
      .status-succeeded {{ border-color: rgba(86, 214, 150, .6); }}
      code {{ color: #c6defe; }}
    </style>
    <script src="https://unpkg.com/htmx.org@2.0.7" integrity="sha384-ZBXiYtYQ6hJ2Y0ZNoYuI+Nq5MqWBr+chMrS/RkXpNzQCApHEhOt2aY8EJgqwHLkJ" crossorigin="anonymous"></script>
    <script>
      function updateSelectedFile(input) {{
        const target = document.querySelector('#selected-file');
        const submit = document.querySelector('#apply-button');
        if (!target) return;
        const hasFile = Boolean(input.files && input.files.length);
        target.textContent = hasFile ? input.files[0].name : 'No file selected';
        if (!submit) return;
        submit.disabled = !hasFile;
        submit.classList.toggle('ready', hasFile);
      }}
      function resetApplyButton() {{
        const submit = document.querySelector('#apply-button');
        const input = document.querySelector('#config-file');
        if (!submit) return;
        const hasFile = Boolean(input && input.files && input.files.length);
        submit.classList.remove('submitting');
        submit.textContent = 'Apply configuration';
        submit.disabled = !hasFile;
        submit.classList.toggle('ready', hasFile);
      }}
      function completeApplyButton() {{
        const submit = document.querySelector('#apply-button');
        if (!submit) return;
        submit.classList.remove('ready');
        submit.classList.remove('submitting');
        submit.textContent = 'Applied';
        submit.disabled = true;
      }}
      window.addEventListener('DOMContentLoaded', () => {{
        const input = document.querySelector('#config-file');
        const dropZone = document.querySelector('#config-drop-zone');
        if (!input || !dropZone) return;
        const stop = (event) => {{ event.preventDefault(); event.stopPropagation(); }};
        dropZone.addEventListener('dragenter', (event) => {{ stop(event); dropZone.classList.add('dragging'); }});
        dropZone.addEventListener('dragover', stop);
        dropZone.addEventListener('dragleave', (event) => {{ stop(event); dropZone.classList.remove('dragging'); }});
        dropZone.addEventListener('drop', (event) => {{
          stop(event);
          dropZone.classList.remove('dragging');
          if (!event.dataTransfer || !event.dataTransfer.files || !event.dataTransfer.files.length) return;
          input.files = event.dataTransfer.files;
          updateSelectedFile(input);
        }});
        document.body.addEventListener('htmx:beforeRequest', (event) => {{
          const form = event.target;
          if (!(form instanceof HTMLFormElement) || form.action.indexOf('/apply') === -1) return;
          const submit = document.querySelector('#apply-button');
          if (!submit) return;
          submit.disabled = true;
          submit.classList.remove('ready');
          submit.classList.add('submitting');
          submit.textContent = 'Applying...';
        }});
      }});
      function startJobStream(jobId) {{
        const target = document.querySelector('#job-status');
        if (!target || !window.EventSource) return;
        if (target.dataset.streamJobId === jobId) return;
        target.dataset.streamJobId = jobId;
        const source = new EventSource(`/ui/jobs/${{encodeURIComponent(jobId)}}/events`);
        source.onmessage = (event) => {{
          if (!event.data) return;
          const nextTarget = document.querySelector('#job-status');
          if (!nextTarget) return;
          nextTarget.outerHTML = event.data;
          const updatedTarget = document.querySelector('#job-status');
          if (updatedTarget) updatedTarget.dataset.streamJobId = jobId;
          const log = updatedTarget && updatedTarget.querySelector('.event-log');
          if (log) log.scrollTop = log.scrollHeight;
        }};
        source.addEventListener('done', () => {{
          source.close();
          const status = document.querySelector('#job-status');
          if (status && status.classList.contains('status-failed')) resetApplyButton();
          else completeApplyButton();
        }});
        source.onerror = () => {{ source.close(); resetApplyButton(); }};
      }}
    </script>
  </head>
  <body>
    <main>
      <section class="hero">
        <img class="hero-mark" src="/assets/atomixos.png" alt="AtomixOS logo">
        <h1>Bootstrap Console</h1>
      </section>
      <section class="grid">
        <form class="panel" method="post" action="/apply" enctype="multipart/form-data" hx-post="/apply" hx-target="#job-status" hx-swap="outerHTML" hx-encoding="multipart/form-data">
          <h2>Load Configuration</h2>
          <p>Upload a <code>config.toml</code> or <code>config.tar.zst</code> or <code>config.tar.gz</code> bundle.</p>
          <input type="hidden" name="bootstrap_token" value="{html.escape(bootstrap_token)}">
          <label id="config-file-label" for="config-file">Config file or bundle</label>
          <div class="file-actions">
            <div class="file-picker"><label class="file-trigger" for="config-file">Choose file</label></div>
            <span class="file-separator">or</span>
            <div id="config-drop-zone" class="drop-zone" aria-label="Drop a config.toml, config.tar.zst, or config.tar.gz bundle here">
              <img class="drop-icon" src="/assets/config_dropzone.png" alt="Drop config file into AtomixOS container">
              <span class="drop-copy">Drop one here</span>
            </div>
          </div>
          <input id="config-file" type="file" name="config_file" aria-labelledby="config-file-label" onchange="updateSelectedFile(this)">
          <div class="apply-row">
            <button id="apply-button" type="submit" disabled>Apply configuration</button>
            <span id="selected-file" class="file-name">No file selected</span>
          </div>
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
    event_html = _render_job_events(snapshot["events"])

    if state in {"submitted", "running"}:
        fragment = _html_page_fragment(
            f"<p><strong>Applying configuration...</strong></p>"
            f"<p>Current stage: <code>{stage}</code></p>"
            f"{event_html}"
        )
        return fragment + f'<script>startJobStream("{html.escape(job.id)}");</script>'

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
            f"{event_html}"
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


def _render_job_events(events: list[dict[str, Any]]) -> str:
    recent_events = events[-40:]
    event_items = "".join(
        "<li>"
        f"<code>{html.escape(str(event['step']))}</code>"
        f"{': ' + html.escape(str(event.get('message', ''))) if event.get('message') else ''}"
        "</li>"
        for event in recent_events
    )
    return f'<div class="event-log"><ol class="events">{event_items}</ol></div>' if event_items else ""


async def _require_unprovisioned(connection, _: Any) -> None:
    """Guard that rejects requests once the device is provisioned."""
    config_root: Path = connection.app.state.config_root
    if _device_is_provisioned(config_root):
        raise NotFoundException()


async def _require_unprovisioned_or_boot_ui_terminal_job(connection, _: Any) -> None:
    config_root: Path = connection.app.state.config_root
    if not _device_is_provisioned(config_root):
        return

    job_id = str(connection.path_params.get("job_id", ""))
    if not job_id:
        raise NotFoundException()

    job_manager: JobManager = connection.app.state.job_manager
    if job_manager.get(job_id) is not None:
        return

    # Provisioning can restart the bootstrap service, which drops in-memory jobs.
    # Once config exists, let the reconnecting Boot UI render terminal success.
    if not (config_root / "config.toml").exists():
        raise NotFoundException()


def _device_is_provisioned(config_root: Path) -> bool:
    return (config_root / "config.toml").exists() or (config_root / "admin-signers").exists()


def _render_recovered_success_fragment() -> str:
    return _html_page_fragment(
        "<p><strong>Configuration applied.</strong></p>"
        "<p>The bootstrap service reconnected after provisioning completed.</p>",
        "status-succeeded",
    )


def _boot_ui_job_state(state: State) -> tuple[set[str], threading.Lock]:
    job_ids = state.setdefault(_BOOT_UI_JOB_IDS, set())
    lock = state.setdefault(_BOOT_UI_JOB_LOCK, threading.Lock())
    return job_ids, lock


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
    logo: Path | None = state.get("logo_path") or _asset_path("atomixos.png")
    if logo and logo.exists():
        content = await asyncio.to_thread(logo.read_bytes)
        return Response(content=content, media_type="image/png")
    return Response(content=b"", status_code=404)


@get("/assets/config_dropzone.png", guards=[_require_unprovisioned], include_in_schema=False)
async def serve_config_dropzone_image(state: State) -> Response[Any]:
    """GET /assets/config_dropzone.png — serve the static drop-zone image."""
    image: Path | None = state.get("config_dropzone_path") or _asset_path("config_dropzone.png")
    if image and image.exists():
        content = await asyncio.to_thread(image.read_bytes)
        return Response(content=content, media_type="image/png")
    return Response(content=b"", status_code=404)


def _asset_path(filename: str) -> Path | None:
    source_path = Path(__file__).resolve().parents[4] / "docs" / "src" / filename
    if source_path.exists():
        return source_path
    installed_path = Path(__file__).resolve().parents[5] / "share" / "atomixos" / filename
    return installed_path if installed_path.exists() else None


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

    boot_ui_jobs, boot_ui_jobs_lock = _boot_ui_job_state(state)
    with boot_ui_jobs_lock:
        boot_ui_jobs.add(job.id)

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
        if (state.config_root / "config.toml").exists():
            return Response(_render_recovered_success_fragment(), media_type="text/html")
        return Response(
            _html_page_fragment("<p>Provisioning job not found.</p>", "status-failed"),
            status_code=404,
            media_type="text/html",
        )
    body = render_job_fragment(job)
    if str(job.snapshot()["state"]) in {"succeeded", "failed"}:
        boot_ui_jobs, boot_ui_jobs_lock = _boot_ui_job_state(state)
        with boot_ui_jobs_lock:
            if (state.config_root / "config.toml").exists() or (
                state.config_root / "admin-signers"
            ).exists():
                if job_id not in boot_ui_jobs:
                    raise NotFoundException()
                boot_ui_jobs.remove(job_id)
    return Response(body, media_type="text/html")


@get(
    "/ui/jobs/{job_id:str}/events",
    guards=[_require_unprovisioned_or_boot_ui_terminal_job],
    include_in_schema=False,
)
async def job_events(job_id: str, job_manager: JobManager, state: State) -> Response[str]:
    """GET /ui/jobs/{id}/events — stream first-boot HTML job status."""
    job = job_manager.get(job_id)
    if job is None:
        if (state.config_root / "config.toml").exists():
            async def recovered_stream():
                yield {"data": _render_recovered_success_fragment()}
                yield {"event": "done", "data": ""}

            return ServerSentEvent(recovered_stream())

        return Response(
            _html_page_fragment("<p>Provisioning job not found.</p>", "status-failed"),
            status_code=404,
            media_type="text/event-stream",
        )

    async def stream():
        last_body = ""
        while True:
            body = render_job_fragment(job)
            if body != last_body:
                yield {"data": body}
                last_body = body
            if str(job.snapshot()["state"]) in {"succeeded", "failed"}:
                yield {"event": "done", "data": ""}
                boot_ui_jobs, boot_ui_jobs_lock = _boot_ui_job_state(state)
                with boot_ui_jobs_lock:
                    if (state.config_root / "config.toml").exists() or (
                        state.config_root / "admin-signers"
                    ).exists():
                        boot_ui_jobs.discard(job_id)
                break
            await asyncio.sleep(0.2)

    return ServerSentEvent(stream())


def ui_routes() -> list:
    """Return the Boot UI route handlers for inclusion in the Litestar app."""
    return [boot_ui, serve_logo, serve_config_dropzone_image, apply_form, job_fragment, job_events]

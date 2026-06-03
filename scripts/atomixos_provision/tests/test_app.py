"""Tests for atomixos_provision.app routes."""

import asyncio
from pathlib import Path

from litestar.testing import AsyncTestClient

from atomixos_provision.app import create_app
from atomixos_provision.config import ProvisionError
from atomixos_provision.jobs import Job, JobManager, JobState, StagedJobManager
from atomixos_provision.staging import reserve_staged_job_slot, runtime_paths

VALID_ED25519_KEY = (
    "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAw"
)


def _job_fragment_url(response_text: str) -> str:
    job_id = response_text.split('startJobStream("')[1].split('"')[0]
    return f"/ui/jobs/{job_id}"


def _job_events_url(response_text: str) -> str:
    return _job_fragment_url(response_text) + "/events"


async def test_nonce_response_returns_nonce(tmp_path):
    async with AsyncTestClient(app=create_app(config_root=tmp_path)) as client:
        response = await client.get("/api/nonce")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"nonce"}
    assert len(body["nonce"]) > 20


def test_data_config_app_uses_staged_job_manager_by_default():
    app = create_app(config_root=Path("/data/config"))

    assert isinstance(app.state.job_manager, StagedJobManager)


def test_resolved_data_config_app_uses_staged_job_manager_by_default(monkeypatch, tmp_path):
    config_root = tmp_path / "data" / "config"
    monkeypatch.setattr(Path, "resolve", lambda self, strict=False: Path("/data/config"))

    app = create_app(config_root=config_root)

    assert isinstance(app.state.job_manager, StagedJobManager)


def test_non_data_config_app_uses_direct_job_manager_by_default(tmp_path):
    app = create_app(config_root=tmp_path)

    assert isinstance(app.state.job_manager, JobManager)
    assert not isinstance(app.state.job_manager, StagedJobManager)


async def test_auth_error_response_uses_framework_shape(tmp_path):
    (tmp_path / "admin-signers").write_text("ssh-ed25519 AAAA test\n")
    app = create_app(config_root=tmp_path)
    async with AsyncTestClient(app=app) as client:
        response = await client.post(
            "/api/config",
            content=b"version = 1\n",
            headers={"x-atomixos-bootstrap-token": app.state.bootstrap_token},
        )

    assert response.status_code == 401
    body = response.json()
    body_text = str(body)
    assert "authentication required" in body_text
    assert "X-AtomixOS-Nonce" in body_text
    assert "X-AtomixOS-Signature" in body_text
    assert "Atomicnix" not in body_text


async def test_config_submission_includes_job_url(tmp_path, monkeypatch):
    async def fake_apply_config_bytes(
        body, filename, config_root, progress=None, allow_reapply=True
    ):
        assert body == b"version = 1\n"
        assert filename == "config.toml"
        assert config_root == tmp_path
        assert allow_reapply is False
        return {"warnings": []}

    monkeypatch.setattr(
        "atomixos_provision.provision.apply_config_bytes",
        fake_apply_config_bytes,
    )

    app = create_app(config_root=tmp_path)
    async with AsyncTestClient(app=app) as client:
        response = await client.post(
            "/api/config",
            content=b"version = 1\n",
            headers={"x-atomixos-bootstrap-token": app.state.bootstrap_token},
        )

    assert response.status_code == 202
    body = response.json()
    assert body["state"] == "submitted"
    assert body["job_url"] == f"/api/jobs/{body['job_id']}"
    assert "poll_token" not in body
    assert response.headers["location"] == body["job_url"]


async def test_first_boot_job_polling_uses_job_url_after_config_exists(tmp_path, monkeypatch):
    async def fake_apply_config_bytes(
        body, filename, config_root, progress=None, allow_reapply=True
    ):
        (tmp_path / "config.toml").write_text("version = 1\n")
        return {"warnings": []}

    monkeypatch.setattr(
        "atomixos_provision.provision.apply_config_bytes",
        fake_apply_config_bytes,
    )

    app = create_app(config_root=tmp_path)
    async with AsyncTestClient(app=app) as client:
        submit = await client.post(
            "/api/config",
            content=b"version = 1\n",
            headers={"x-atomixos-bootstrap-token": app.state.bootstrap_token},
        )
        body = submit.json()
        response = await client.get(body["job_url"])

    assert response.status_code == 200


async def test_first_boot_config_submit_accepts_programmatic_upload_without_token(
    tmp_path, monkeypatch
):
    async def fake_apply_config_bytes(
        body, filename, config_root, progress=None, allow_reapply=True
    ):
        assert body == b"version = 1\n"
        assert allow_reapply is False
        return {"warnings": []}

    monkeypatch.setattr(
        "atomixos_provision.provision.apply_config_bytes",
        fake_apply_config_bytes,
    )

    async with AsyncTestClient(app=create_app(config_root=tmp_path)) as client:
        response = await client.post("/api/config", content=b"version = 1\n")

    assert response.status_code == 202


async def test_config_submit_accepts_zstd_magic_without_filename_header(tmp_path, monkeypatch):
    async def fake_stage_bytes(self, body, filename, progress, allow_reapply=True):
        assert body.startswith(b"\x28\xb5\x2f\xfd")
        assert filename == "config.toml"

    manager = StagedJobManager()
    monkeypatch.setenv("ATOMIXOS_PROVISION_RUNTIME_DIR", str(tmp_path / "run"))
    monkeypatch.setattr(manager, "_refresh_from_result", lambda job: True)
    monkeypatch.setattr(
        "atomixos_provision.domain.config.service.ConfigService.stage_bytes",
        fake_stage_bytes,
    )
    app = create_app(config_root=tmp_path, job_manager=manager)

    async with AsyncTestClient(app=app) as client:
        response = await client.post("/api/config", content=b"\x28\xb5\x2f\xfdpayload")

    assert response.status_code == 202


async def test_config_submit_records_staging_provision_errors_as_failed_job(
    tmp_path, monkeypatch
):
    async def fake_stage_bytes(self, body, filename, progress, allow_reapply=True):
        raise ProvisionError("bad bundle")

    manager = StagedJobManager()
    monkeypatch.setenv("ATOMIXOS_PROVISION_RUNTIME_DIR", str(tmp_path / "run"))
    monkeypatch.setattr(
        "atomixos_provision.domain.config.service.ConfigService.stage_bytes",
        fake_stage_bytes,
    )
    app = create_app(config_root=tmp_path, job_manager=manager)

    async with AsyncTestClient(app=app) as client:
        response = await client.post("/api/config", content=b"\x28\xb5\x2f\xfdpayload")
        job_response = await client.get(response.json()["job_url"])

    assert response.status_code == 202
    assert job_response.status_code == 200
    assert job_response.json()["state"] == "failed"
    assert job_response.json()["error"] == "bad bundle"


async def test_get_job_rejects_malformed_staged_job_id(tmp_path):
    app = create_app(config_root=tmp_path, job_manager=StagedJobManager())
    async with AsyncTestClient(app=app) as client:
        response = await client.get("/api/jobs/bad%20id")

    assert response.status_code == 404
    assert response.json() == {"error": "job not found"}


async def test_first_boot_config_submit_rejects_missing_host(tmp_path):
    async with AsyncTestClient(app=create_app(config_root=tmp_path)) as client:
        response = await client.post(
            "/api/config",
            content=b"version = 1\n",
            headers={"host": ""},
        )

    assert response.status_code == 401


async def test_first_boot_config_submit_rejects_invalid_host(tmp_path):
    async with AsyncTestClient(app=create_app(config_root=tmp_path)) as client:
        response = await client.post(
            "/api/config",
            content=b"version = 1\n",
            headers={"host": "evil.example"},
        )

    assert response.status_code == 401


async def test_first_boot_config_submit_rejects_invalid_host_port(tmp_path):
    async with AsyncTestClient(app=create_app(config_root=tmp_path)) as client:
        response = await client.post(
            "/api/config",
            content=b"version = 1\n",
            headers={"host": "172.20.30.1:notaport"},
        )

    assert response.status_code == 401


async def test_first_boot_config_submit_rejects_mismatched_origin(tmp_path):
    app = create_app(config_root=tmp_path)
    async with AsyncTestClient(app=app) as client:
        response = await client.post(
            "/api/config",
            content=b"version = 1\n",
            headers={
                "host": "172.20.30.1:8080",
                "origin": "http://localhost:8080",
            },
        )

    assert response.status_code == 401


async def test_first_boot_config_submit_rejects_mismatched_origin_port(tmp_path):
    app = create_app(config_root=tmp_path)
    async with AsyncTestClient(app=app) as client:
        response = await client.post(
            "/api/config",
            content=b"version = 1\n",
            headers={
                "host": "172.20.30.1:8080",
                "origin": "http://172.20.30.1:9999",
            },
        )

    assert response.status_code == 401


async def test_first_boot_config_submit_rejects_malformed_origin(tmp_path):
    app = create_app(config_root=tmp_path)
    async with AsyncTestClient(app=app) as client:
        response = await client.post(
            "/api/config",
            content=b"version = 1\n",
            headers={
                "host": "172.20.30.1:8080",
                "origin": "null",
            },
        )

    assert response.status_code == 401


async def test_first_boot_config_submit_rejects_invalid_origin_port(tmp_path):
    app = create_app(config_root=tmp_path)
    async with AsyncTestClient(app=app) as client:
        response = await client.post(
            "/api/config",
            content=b"version = 1\n",
            headers={
                "host": "172.20.30.1:8080",
                "origin": "http://172.20.30.1:notaport",
            },
        )

    assert response.status_code == 401


async def test_first_boot_config_submit_rejects_malformed_referer(tmp_path):
    app = create_app(config_root=tmp_path)
    async with AsyncTestClient(app=app) as client:
        response = await client.post(
            "/api/config",
            content=b"version = 1\n",
            headers={
                "host": "172.20.30.1:8080",
                "referer": "http://[::1",
            },
        )

    assert response.status_code == 401


async def test_validate_requires_auth_even_before_provisioning(tmp_path):
    async with AsyncTestClient(app=create_app(config_root=tmp_path)) as client:
        response = await client.post("/api/validate", content=b"version = 1\n")

    assert response.status_code == 401


async def test_partial_config_update_requires_auth_even_before_provisioning(tmp_path):
    async with AsyncTestClient(app=create_app(config_root=tmp_path)) as client:
        response = await client.put(
            "/api/config/users/alice",
            json={"isAdmin": False, "ssh_key": "ssh-ed25519 AAAA alice"},
        )

    assert response.status_code == 401


async def test_config_export_requires_auth(tmp_path):
    (tmp_path / "config.toml").write_text("version = 1\n")
    async with AsyncTestClient(app=create_app(config_root=tmp_path)) as client:
        response = await client.get("/api/config/export")

    assert response.status_code == 401


async def test_partial_config_rejects_unknown_top_level_keys(tmp_path, monkeypatch):
    async def fake_apply_config_operation(operation, config_root, progress=None):
        from atomixos_provision.partial_config import apply_operation

        apply_operation({"version": 1}, operation)

    class AcceptingNonceStore:
        async def consume(self, nonce):
            return nonce == "test"

    (tmp_path / "admin-signers").write_text("ssh-ed25519 AAAA test\n")
    monkeypatch.setenv("ATOMIXOS_PROVISION_RUNTIME_DIR", str(tmp_path / "run"))
    monkeypatch.setattr(
        "atomixos_provision.provision.apply_config_operation",
        fake_apply_config_operation,
    )
    monkeypatch.setattr(
        "atomixos_provision.auth.verify_ssh_signature",
        lambda message, signature_blob, allowed_keys_path: True,
    )

    app = create_app(config_root=tmp_path)
    app.state.nonce_store = AcceptingNonceStore()
    async with AsyncTestClient(app=app) as client:
        response = await client.put(
            "/api/config/container-networks/podnet",
            json={"Network": {}, "Container": {}},
            headers={
                "x-atomixos-nonce": "test",
                "x-atomixos-signature": "dGVzdA==",
            },
        )

    assert response.status_code == 202
    job = response.json()

    async with AsyncTestClient(app=app) as client:
        result = await client.get(job["job_url"])

    assert result.status_code == 200
    body = result.json()
    assert body["state"] == "failed"
    assert body["error"] == "unsupported partial request keys: Container"


async def test_partial_config_uses_staged_job_manager_when_available(tmp_path, monkeypatch):
    class AcceptingNonceStore:
        async def consume(self, nonce):
            return nonce == "test"

    calls = {}

    async def fake_stage_config_operation(job_id, operation, config_root, progress=None):
        calls["job_id"] = job_id
        calls["operation"] = operation
        calls["config_root"] = config_root

    (tmp_path / "admin-signers").write_text("ssh-ed25519 AAAA test\n")
    monkeypatch.setenv("ATOMIXOS_PROVISION_RUNTIME_DIR", str(tmp_path / "run"))
    monkeypatch.setattr(
        "atomixos_provision.provision.stage_config_operation",
        fake_stage_config_operation,
    )
    monkeypatch.setattr(
        "atomixos_provision.auth.verify_ssh_signature",
        lambda message, signature_blob, allowed_keys_path: True,
    )
    monkeypatch.setattr(
        "atomixos_provision.jobs.StagedJobManager._refresh_from_result",
        lambda self, job: True,
    )

    app = create_app(config_root=tmp_path, job_manager=StagedJobManager())
    app.state.nonce_store = AcceptingNonceStore()
    async with AsyncTestClient(app=app) as client:
        response = await client.put(
            "/api/config/users/alice",
            json={"isAdmin": False, "ssh_key": "ssh-ed25519 AAAA alice"},
            headers={
                "x-atomixos-nonce": "test",
                "x-atomixos-signature": "dGVzdA==",
            },
        )

    assert response.status_code == 202
    assert calls["job_id"] == response.json()["job_id"]
    assert calls["config_root"] == tmp_path
    assert calls["operation"] == {
        "op": "put_user",
        "name": "alice",
        "payload": {"isAdmin": False, "ssh_key": "ssh-ed25519 AAAA alice"},
    }


async def test_partial_config_reports_full_staged_queue(tmp_path, monkeypatch):
    class AcceptingNonceStore:
        async def consume(self, nonce):
            return nonce == "test"

    async def fake_stage_config_operation(job_id, operation, config_root, progress=None):
        return None

    (tmp_path / "admin-signers").write_text("ssh-ed25519 AAAA test\n")
    monkeypatch.setenv("ATOMIXOS_PROVISION_RUNTIME_DIR", str(tmp_path / "run"))
    monkeypatch.setattr(
        "atomixos_provision.provision.stage_config_operation",
        fake_stage_config_operation,
    )
    monkeypatch.setattr(
        "atomixos_provision.auth.verify_ssh_signature",
        lambda message, signature_blob, allowed_keys_path: True,
    )

    manager = StagedJobManager(max_pending=1)
    monkeypatch.setattr(manager, "_refresh_from_result", lambda job: True)
    app = create_app(config_root=tmp_path, job_manager=manager)
    app.state.nonce_store = AcceptingNonceStore()
    async with AsyncTestClient(app=app) as client:
        first = await client.put(
            "/api/config/users/alice",
            json={"isAdmin": False, "ssh_key": "ssh-ed25519 AAAA alice"},
            headers={"x-atomixos-nonce": "test", "x-atomixos-signature": "dGVzdA=="},
        )
        second = await client.put(
            "/api/config/users/bob",
            json={"isAdmin": False, "ssh_key": "ssh-ed25519 AAAA bob"},
            headers={"x-atomixos-nonce": "test", "x-atomixos-signature": "dGVzdA=="},
        )

    assert first.status_code == 202
    assert second.status_code == 409
    assert second.json() == {"error": "the provision queue is full"}


async def test_partial_config_rejects_when_staged_queue_not_empty(tmp_path, monkeypatch):
    class AcceptingNonceStore:
        async def consume(self, nonce):
            return nonce == "test"

    runtime_root = tmp_path / "run"
    (tmp_path / "admin-signers").write_text("ssh-ed25519 AAAA test\n")
    (tmp_path / "config.toml").write_text(
        f"""\
version = 1

[users.admin]
isAdmin = true
ssh_key = "{VALID_ED25519_KEY} admin@example"

[activation]
required = ["app"]

[containers.container.app]
privileged = false

[containers.container.app.Container]
Image = "docker.io/library/alpine:latest"
"""
    )
    monkeypatch.setenv("ATOMIXOS_PROVISION_RUNTIME_DIR", str(runtime_root))
    monkeypatch.setattr(
        "atomixos_provision.auth.verify_ssh_signature",
        lambda message, signature_blob, allowed_keys_path: True,
    )
    assert reserve_staged_job_slot(runtime_paths(runtime_root), "other-job", 2) is True

    app = create_app(config_root=tmp_path, job_manager=StagedJobManager(max_pending=2))
    app.state.nonce_store = AcceptingNonceStore()
    async with AsyncTestClient(app=app) as client:
        response = await client.put(
            "/api/config/users/alice",
            json={"isAdmin": False, "ssh_key": "ssh-ed25519 AAAA alice"},
            headers={"x-atomixos-nonce": "test", "x-atomixos-signature": "dGVzdA=="},
        )

    assert response.status_code == 409
    assert response.json() == {"error": "the provision queue is full"}


async def test_boot_ui_serves_configuration_forms(tmp_path):
    async with AsyncTestClient(app=create_app(config_root=tmp_path)) as client:
        response = await client.get("/")

    assert response.status_code == 200
    body = response.text
    assert "Load Configuration" in body
    assert "Apply Existing Configuration" not in body
    assert "Import an existing" not in body
    assert "config.tar.zst" in body
    assert "config.tar.gz" in body
    assert "htmx.org" in body
    assert 'hx-post="/apply"' in body
    assert 'hx-target="#job-status"' in body
    assert "htmx:beforeRequest" in body
    assert "nextTarget.outerHTML = event.data" in body
    assert "updatedTarget.dataset.streamJobId = jobId" in body
    assert "target.outerHTML = event.data" not in body
    assert "function resetApplyButton()" in body
    assert "function completeApplyButton()" in body
    assert "status.classList.contains('status-failed')" in body
    assert "else completeApplyButton();" in body
    assert "source.onerror = () => { source.close(); resetApplyButton(); };" in body
    assert "Applying..." in body
    assert "submitting" in body
    assert "Choose file" in body
    assert '<span class="file-separator">or</span>' in body
    assert "No file selected" in body
    assert "Drop a config.toml" in body
    assert "Drop one here" in body
    assert 'src="/assets/config_dropzone.png"' in body
    assert "config.toml</label><textarea" not in body
    assert "disabled>Apply configuration" in body
    assert 'name="config_file"' in body
    assert "Generate New Configuration" not in body
    assert "Download signing challenge" not in body
    assert "atomixos-reapply-challenge" not in body
    assert "auth_signature" not in body


async def test_boot_ui_escapes_applied_config_download_script(tmp_path, monkeypatch):
    async def fake_apply_config_bytes(
        body, filename, config_root, progress=None, allow_reapply=True
    ):
        return {"warnings": []}

    monkeypatch.setattr(
        "atomixos_provision.provision.apply_config_bytes",
        fake_apply_config_bytes,
    )

    app = create_app(config_root=tmp_path)
    payload = "version = 1\n# </script><script>alert(1)</script>\n"
    upload = {"config_file": ("config.toml", payload, "text/plain")}
    async with AsyncTestClient(app=app) as client:
        response = await client.post(
            "/apply",
            data={"bootstrap_token": app.state.bootstrap_token},
            files=upload,
        )

    assert response.status_code == 200
    assert "# &lt;/script&gt;&lt;script&gt;alert(1)&lt;/script&gt;" in response.text
    assert "# <\\/script><script>alert(1)<\\/script>" in response.text
    assert "# </script><script>alert(1)</script>" not in response.text


async def test_apply_form_htmx_upload_success_returns_fragment(tmp_path, monkeypatch):
    async def fake_apply_config_bytes(
        body, filename, config_root, progress=None, allow_reapply=True
    ):
        return {"warnings": []}

    monkeypatch.setattr(
        "atomixos_provision.provision.apply_config_bytes",
        fake_apply_config_bytes,
    )

    app = create_app(config_root=tmp_path)
    upload = {"config_file": ("config.toml", "version = 1\n", "text/plain")}
    async with AsyncTestClient(app=app) as client:
        response = await client.post(
            "/apply",
            data={"bootstrap_token": app.state.bootstrap_token},
            files=upload,
            headers={"HX-Request": "true"},
        )

    assert response.status_code == 200
    assert response.text.startswith('<section id="job-status"')
    assert "Configuration applied" in response.text
    assert "completeApplyButton();" in response.text
    assert "resetApplyButton();" not in response.text
    assert "<!doctype html>" not in response.text
    assert "Download applied config.toml" not in response.text


async def test_apply_form_htmx_upload_failure_returns_fragment(tmp_path, monkeypatch):
    async def fake_apply_config_bytes(
        body, filename, config_root, progress=None, allow_reapply=True
    ):
        raise ProvisionError("invalid config")

    monkeypatch.setattr(
        "atomixos_provision.provision.apply_config_bytes",
        fake_apply_config_bytes,
    )

    app = create_app(config_root=tmp_path)
    upload = {"config_file": ("config.toml", "version = 1\n", "text/plain")}
    async with AsyncTestClient(app=app) as client:
        response = await client.post(
            "/apply",
            data={"bootstrap_token": app.state.bootstrap_token},
            files=upload,
            headers={"HX-Request": "true"},
        )

    assert response.status_code == 200
    assert response.text.startswith('<section id="job-status"')
    assert "Configuration failed" in response.text
    assert "invalid config" in response.text
    assert "resetApplyButton();" in response.text
    assert "completeApplyButton();" not in response.text
    assert "<!doctype html>" not in response.text


async def test_apply_form_returns_async_job_fragment(tmp_path, monkeypatch):
    started = asyncio.Event()
    finish = asyncio.Event()

    async def fake_apply_config_bytes(
        body, filename, config_root, progress=None, allow_reapply=True
    ):
        assert body == b"version = 1\n"
        assert filename == "config.toml"
        assert config_root == tmp_path
        assert allow_reapply is False
        started.set()
        await finish.wait()
        return {"warnings": ["careful"], "forwarding_url": "http://172.20.30.1:8080"}

    monkeypatch.setattr(
        "atomixos_provision.provision.apply_config_bytes",
        fake_apply_config_bytes,
    )

    app = create_app(config_root=tmp_path)
    async with AsyncTestClient(app=app) as client:
        response = await client.post(
            "/apply",
            data={"bootstrap_token": app.state.bootstrap_token, "config": "version = 1\n"},
        )

        assert response.status_code == 202
        assert "Applying configuration" in response.text
        assert "startJobStream(" in response.text
        await asyncio.wait_for(started.wait(), timeout=1)
        finish.set()

        async def poll_until_done():
            for _ in range(20):
                fragment = await client.get(_job_fragment_url(response.text))
                if "Configuration applied" in fragment.text:
                    return fragment
                await asyncio.sleep(0.05)
            raise AssertionError("job did not complete")

        fragment = await poll_until_done()

    assert fragment.status_code == 200
    assert "careful" in fragment.text
    assert "http://172.20.30.1:8080" in fragment.text


async def test_apply_form_uses_pasted_config_when_no_file_selected(tmp_path, monkeypatch):
    async def fake_apply_config_bytes(
        body, filename, config_root, progress=None, allow_reapply=True
    ):
        assert body == b"version = 1\n"
        assert filename == "config.toml"
        return {"warnings": []}

    monkeypatch.setattr(
        "atomixos_provision.provision.apply_config_bytes",
        fake_apply_config_bytes,
    )

    app = create_app(config_root=tmp_path)
    async with AsyncTestClient(app=app) as client:
        response = await client.post(
            "/apply",
            data={"bootstrap_token": app.state.bootstrap_token, "config": "version = 1\n"},
        )
        fragment_url = _job_fragment_url(response.text)

        async def poll_until_done():
            for _ in range(20):
                fragment = await client.get(fragment_url)
                if "Configuration applied" in fragment.text:
                    return fragment
                await asyncio.sleep(0.05)
            raise AssertionError("job did not complete")

        fragment = await poll_until_done()

    assert response.status_code == 202
    assert fragment.status_code == 200


async def test_apply_form_renders_failure_and_rollback(tmp_path, monkeypatch):
    async def fake_apply_config_bytes(
        body, filename, config_root, progress=None, allow_reapply=True
    ):
        exc = ProvisionError("activation failed: app.service")
        exc.rollback_status = "completed"
        raise exc

    monkeypatch.setattr(
        "atomixos_provision.provision.apply_config_bytes",
        fake_apply_config_bytes,
    )

    app = create_app(config_root=tmp_path)
    async with AsyncTestClient(app=app) as client:
        response = await client.post(
            "/apply",
            data={"bootstrap_token": app.state.bootstrap_token, "config": "version = 1\n"},
        )
        fragment_url = _job_fragment_url(response.text)

        async def poll_until_failed():
            for _ in range(20):
                fragment = await client.get(fragment_url)
                if "Configuration failed" in fragment.text:
                    return fragment
                await asyncio.sleep(0.05)
            raise AssertionError("job did not fail")

        fragment = await poll_until_failed()

    assert response.status_code == 202
    assert fragment.status_code == 200
    assert "activation failed: app.service" in fragment.text
    assert "Rollback status:</strong> completed" in fragment.text


async def test_apply_form_can_render_terminal_fragment_after_provisioning(
    tmp_path, monkeypatch
):
    started = asyncio.Event()
    finish = asyncio.Event()

    async def fake_apply_config_bytes(
        body, filename, config_root, progress=None, allow_reapply=True
    ):
        started.set()
        await finish.wait()
        (tmp_path / "config.toml").write_text("version = 1\n")
        return {"warnings": [], "forwarding_url": "http://172.20.30.1:8080"}

    monkeypatch.setattr(
        "atomixos_provision.provision.apply_config_bytes",
        fake_apply_config_bytes,
    )

    app = create_app(config_root=tmp_path)
    async with AsyncTestClient(app=app) as client:
        response = await client.post(
            "/apply",
            data={"bootstrap_token": app.state.bootstrap_token, "config": "version = 1\n"},
        )
        await asyncio.wait_for(started.wait(), timeout=1)
        finish.set()
        fragment_url = _job_fragment_url(response.text)

        async def poll_until_done():
            for _ in range(20):
                fragment = await client.get(fragment_url)
                if "Configuration applied" in fragment.text:
                    return fragment
                await asyncio.sleep(0.05)
            raise AssertionError("job did not complete")

        terminal = await poll_until_done()
        second_terminal = await client.get(fragment_url)

    assert terminal.status_code == 200
    assert "http://172.20.30.1:8080" in terminal.text
    assert second_terminal.status_code == 404


async def test_boot_ui_job_fragment_recovers_after_service_restart(tmp_path, monkeypatch):
    from atomixos_provision.ui import _remember_boot_ui_job

    runtime_root = tmp_path / "run"
    monkeypatch.setenv("ATOMIXOS_PROVISION_RUNTIME_DIR", str(runtime_root))
    (tmp_path / "config.toml").write_text("version = 1\n")
    _remember_boot_ui_job("restarted-job")

    async with AsyncTestClient(app=create_app(config_root=tmp_path)) as client:
        response = await client.get("/ui/jobs/restarted-job")
        second = await client.get("/ui/jobs/restarted-job")

    assert response.status_code == 200
    assert "Configuration applied" in response.text
    assert "reconnected after provisioning completed" in response.text
    assert second.status_code == 404


async def test_boot_ui_terminal_fragment_accepts_persisted_marker_after_restart(
    tmp_path, monkeypatch
):
    from atomixos_provision.ui import _remember_boot_ui_job

    runtime_root = tmp_path / "run"
    monkeypatch.setenv("ATOMIXOS_PROVISION_RUNTIME_DIR", str(runtime_root))
    (tmp_path / "config.toml").write_text("version = 1\n")
    _remember_boot_ui_job("terminal-job")
    app = create_app(config_root=tmp_path)
    app.state.job_manager._jobs["terminal-job"] = Job(
        id="terminal-job",
        state=JobState.SUCCEEDED,
        result={"forwarding_url": "http://172.20.30.1:8080"},
    )

    async with AsyncTestClient(app=app) as client:
        response = await client.get("/ui/jobs/terminal-job")
        second = await client.get("/ui/jobs/terminal-job")

    assert response.status_code == 200
    assert "Configuration applied" in response.text
    assert second.status_code == 404


async def test_apply_form_keeps_polling_after_config_appears(tmp_path, monkeypatch):
    started = asyncio.Event()
    finish = asyncio.Event()

    async def fake_apply_config_bytes(
        body, filename, config_root, progress=None, allow_reapply=True
    ):
        (tmp_path / "config.toml").write_text("version = 1\n")
        started.set()
        await finish.wait()
        return {"warnings": [], "forwarding_url": "http://172.20.30.1:8080"}

    monkeypatch.setattr(
        "atomixos_provision.provision.apply_config_bytes",
        fake_apply_config_bytes,
    )

    app = create_app(config_root=tmp_path)
    async with AsyncTestClient(app=app) as client:
        response = await client.post(
            "/apply",
            data={"bootstrap_token": app.state.bootstrap_token, "config": "version = 1\n"},
        )
        await asyncio.wait_for(started.wait(), timeout=1)
        fragment_url = _job_fragment_url(response.text)
        running_fragment = await client.get(fragment_url)
        finish.set()

    assert response.status_code == 202
    assert running_fragment.status_code == 200
    assert "Applying configuration" in running_fragment.text


async def test_job_events_streams_status_fragments(tmp_path, monkeypatch):
    started = asyncio.Event()
    finish = asyncio.Event()

    async def fake_apply_config_bytes(
        body, filename, config_root, progress=None, allow_reapply=True
    ):
        started.set()
        progress.set_stage("activate", "starting services")
        await finish.wait()
        return {"warnings": [], "forwarding_url": "http://172.20.30.1:8080"}

    monkeypatch.setattr(
        "atomixos_provision.provision.apply_config_bytes",
        fake_apply_config_bytes,
    )

    app = create_app(config_root=tmp_path)
    async with AsyncTestClient(app=app) as client:
        response = await client.post(
            "/apply",
            data={"bootstrap_token": app.state.bootstrap_token, "config": "version = 1\n"},
        )
        await asyncio.wait_for(started.wait(), timeout=1)
        finish.set()
        stream = await client.get(_job_events_url(response.text))

    assert response.status_code == 202
    assert stream.status_code == 200
    assert stream.headers["content-type"].startswith("text/event-stream")
    assert "data: <section id=\"job-status\"" in stream.text
    assert "data: data:" not in stream.text
    assert "Configuration applied" in stream.text
    assert "event: done" in stream.text


async def test_boot_ui_job_events_include_render_steps(tmp_path, monkeypatch):
    config = f"""
version = 1
[users.admin]
isAdmin = true
ssh_key = "{VALID_ED25519_KEY} admin@test"

[network.interfaces.eth1]
mode = "static"
address = "172.20.30.1/24"

[activation]
required = ["web"]

[containers.container.web]
privileged = false

[containers.container.web.Container]
Image = "ghcr.io/example/web:latest"
""".strip()

    monkeypatch.setenv("ATOMIXOS_ALLOW_UNSAFE_CONFIG_ROOT", "1")
    app = create_app(config_root=tmp_path)
    async with AsyncTestClient(app=app) as client:
        response = await client.post(
            "/apply",
            data={"bootstrap_token": app.state.bootstrap_token, "config": config},
        )
        stream = await client.get(_job_events_url(response.text))

    assert response.status_code == 202
    assert stream.status_code == 200
    assert "<code>prepare</code>: unpacking config.toml" in stream.text
    assert "<code>write-users</code>: rendering user accounts" in stream.text
    assert "<code>write-network</code>: rendering host network settings" in stream.text
    assert "<code>render-containers</code>: rendering containers" in stream.text
    assert "<code>write-quadlets</code>: writing container unit files" in stream.text


async def test_job_events_recovers_after_service_restart(tmp_path, monkeypatch):
    from atomixos_provision.ui import _remember_boot_ui_job

    runtime_root = tmp_path / "run"
    monkeypatch.setenv("ATOMIXOS_PROVISION_RUNTIME_DIR", str(runtime_root))
    (tmp_path / "config.toml").write_text("version = 1\n")
    _remember_boot_ui_job("restarted-job")

    async with AsyncTestClient(app=create_app(config_root=tmp_path)) as client:
        stream = await client.get("/ui/jobs/restarted-job/events")
        second = await client.get("/ui/jobs/restarted-job/events")

    assert stream.status_code == 200
    assert stream.headers["content-type"].startswith("text/event-stream")
    assert "Configuration applied" in stream.text
    assert "event: done" in stream.text
    assert second.status_code == 404


async def test_apply_form_reports_conflict_while_job_running(tmp_path, monkeypatch):
    finish = asyncio.Event()

    async def fake_apply_config_bytes(
        body, filename, config_root, progress=None, allow_reapply=True
    ):
        await finish.wait()
        return {"warnings": []}

    monkeypatch.setattr(
        "atomixos_provision.provision.apply_config_bytes",
        fake_apply_config_bytes,
    )

    app = create_app(config_root=tmp_path)
    async with AsyncTestClient(app=app) as client:
        first = await client.post(
            "/apply",
            data={"bootstrap_token": app.state.bootstrap_token, "config": "version = 1\n"},
        )
        second = await client.post(
            "/apply",
            data={"bootstrap_token": app.state.bootstrap_token, "config": "version = 1\n"},
        )
        finish.set()

    assert first.status_code == 202
    assert second.status_code == 409
    assert "already running" in second.text


async def test_apply_form_rejects_invalid_bootstrap_token(tmp_path):
    async with AsyncTestClient(app=create_app(config_root=tmp_path)) as client:
        response = await client.post(
            "/apply",
            data={"bootstrap_token": "wrong", "config": "version = 1\n"},
        )

    assert response.status_code == 403


async def test_apply_form_rejects_mismatched_origin(tmp_path):
    app = create_app(config_root=tmp_path)
    async with AsyncTestClient(app=app) as client:
        response = await client.post(
            "/apply",
            data={"bootstrap_token": app.state.bootstrap_token, "config": "version = 1\n"},
            headers={
                "host": "172.20.30.1:8080",
                "origin": "http://localhost:8080",
            },
        )

    assert response.status_code == 401


async def test_apply_form_rejects_malformed_origin(tmp_path):
    app = create_app(config_root=tmp_path)
    async with AsyncTestClient(app=app) as client:
        response = await client.post(
            "/apply",
            data={"bootstrap_token": app.state.bootstrap_token, "config": "version = 1\n"},
            headers={
                "host": "172.20.30.1:8080",
                "origin": "http://[::1",
            },
        )

    assert response.status_code == 401


async def test_ui_job_fragment_returns_404_on_provisioned_device(tmp_path):
    (tmp_path / "admin-signers").write_text("ssh-ed25519 AAAA test\n")
    async with AsyncTestClient(app=create_app(config_root=tmp_path)) as client:
        response = await client.get("/ui/jobs/missing")

    assert response.status_code == 404


async def test_logo_returns_404_on_provisioned_device(tmp_path):
    (tmp_path / "admin-signers").write_text("ssh-ed25519 AAAA test\n")
    async with AsyncTestClient(app=create_app(config_root=tmp_path)) as client:
        response = await client.get("/assets/atomixos.png")

    assert response.status_code == 404


async def test_config_dropzone_image_returns_404_on_provisioned_device(tmp_path):
    (tmp_path / "admin-signers").write_text("ssh-ed25519 AAAA test\n")
    async with AsyncTestClient(app=create_app(config_root=tmp_path)) as client:
        response = await client.get("/assets/config_dropzone.png")

    assert response.status_code == 404


async def test_apply_form_returns_404_on_provisioned_device(tmp_path):
    (tmp_path / "admin-signers").write_text("ssh-ed25519 AAAA test\n")
    async with AsyncTestClient(app=create_app(config_root=tmp_path)) as client:
        response = await client.post("/apply", data={"config": "version = 1\n"})

    assert response.status_code == 404


async def test_boot_ui_returns_404_on_provisioned_device(tmp_path):
    (tmp_path / "admin-signers").write_text("ssh-ed25519 AAAA test\n")
    async with AsyncTestClient(app=create_app(config_root=tmp_path)) as client:
        response = await client.get("/")

    assert response.status_code == 404


async def test_boot_ui_returns_404_when_config_exists_without_signers(tmp_path):
    (tmp_path / "config.toml").write_text("version = 1\n")
    async with AsyncTestClient(app=create_app(config_root=tmp_path)) as client:
        response = await client.get("/")

    assert response.status_code == 404


async def test_boot_ui_rejects_unknown_terminal_job_after_provisioning(tmp_path):
    (tmp_path / "config.toml").write_text("version = 1\n")

    async with AsyncTestClient(app=create_app(config_root=tmp_path)) as client:
        fragment = await client.get("/ui/jobs/unknown-job")
        stream = await client.get("/ui/jobs/unknown-job/events")

    assert fragment.status_code == 404
    assert stream.status_code == 404


async def test_boot_ui_rejects_malformed_terminal_job_after_provisioning(tmp_path):
    (tmp_path / "config.toml").write_text("version = 1\n")

    async with AsyncTestClient(app=create_app(config_root=tmp_path)) as client:
        fragment = await client.get("/ui/jobs/../bad")
        stream = await client.get("/ui/jobs/../bad/events")

    assert fragment.status_code == 404
    assert stream.status_code == 404


async def test_openapi_documents_public_api_contract(tmp_path):
    async with AsyncTestClient(app=create_app(config_root=tmp_path)) as client:
        response = await client.get("/schema/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    assert {
        path: set(methods)
        for path, methods in schema["paths"].items()
    } == {
        "/api/health": {"get"},
        "/api/nonce": {"get"},
        "/api/config": {"post"},
        "/api/config/export": {"get"},
        "/api/config/users/{name}": {"put", "delete"},
        "/api/config/network": {"patch"},
        "/api/config/containers/{name}": {"put", "delete"},
        "/api/config/container-networks/{name}": {"put", "delete"},
        "/api/config/container-volumes/{name}": {"put", "delete"},
        "/api/validate": {"post"},
        "/api/jobs/{job_id}": {"get"},
    }

    health = schema["paths"]["/api/health"]["get"]
    nonce = schema["paths"]["/api/nonce"]["get"]
    submit = schema["paths"]["/api/config"]["post"]
    export = schema["paths"]["/api/config/export"]["get"]
    put_user = schema["paths"]["/api/config/users/{name}"]["put"]
    delete_user = schema["paths"]["/api/config/users/{name}"]["delete"]
    patch_network = schema["paths"]["/api/config/network"]["patch"]
    put_container = schema["paths"]["/api/config/containers/{name}"]["put"]
    delete_container = schema["paths"]["/api/config/containers/{name}"]["delete"]
    put_container_network = schema["paths"]["/api/config/container-networks/{name}"]["put"]
    delete_container_network = schema["paths"]["/api/config/container-networks/{name}"]["delete"]
    put_container_volume = schema["paths"]["/api/config/container-volumes/{name}"]["put"]
    delete_container_volume = schema["paths"]["/api/config/container-volumes/{name}"]["delete"]
    validate = schema["paths"]["/api/validate"]["post"]
    get_job = schema["paths"]["/api/jobs/{job_id}"]["get"]

    assert health["operationId"] == "systemHealth"
    assert health["tags"] == ["system"]
    assert nonce["operationId"] == "authIssueNonce"
    assert nonce["tags"] == ["auth"]
    assert submit["operationId"] == "configSubmit"
    assert submit["tags"] == ["config"]
    assert export["operationId"] == "configExport"
    assert export["tags"] == ["config"]
    assert put_user["operationId"] == "configUsersPut"
    assert delete_user["operationId"] == "configUsersDelete"
    assert patch_network["operationId"] == "configNetworkPatch"
    assert put_container["operationId"] == "configContainersPut"
    assert delete_container["operationId"] == "configContainersDelete"
    assert put_container_network["operationId"] == "configContainerNetworksPut"
    assert delete_container_network["operationId"] == "configContainerNetworksDelete"
    assert put_container_volume["operationId"] == "configContainerVolumesPut"
    assert delete_container_volume["operationId"] == "configContainerVolumesDelete"
    assert {operation["tags"][0] for operation in [
        put_user,
        delete_user,
        patch_network,
        put_container,
        delete_container,
        put_container_network,
        delete_container_network,
        put_container_volume,
        delete_container_volume,
    ]} == {"config"}
    assert validate["operationId"] == "configValidate"
    assert validate["tags"] == ["config"]
    assert get_job["operationId"] == "jobsGet"
    assert get_job["tags"] == ["jobs"]

    assert submit["requestBody"]["content"]["application/octet-stream"]["schema"] == {
        "type": "string",
        "format": "binary",
    }
    assert validate["requestBody"] == submit["requestBody"]

    submit_headers = {param["name"]: param for param in submit["parameters"]}
    validate_headers = {param["name"]: param for param in validate["parameters"]}
    job_headers = {param["name"]: param for param in get_job["parameters"]}
    authenticated_operations = [
        export,
        put_user,
        delete_user,
        patch_network,
        put_container,
        delete_container,
        put_container_network,
        delete_container_network,
        put_container_volume,
        delete_container_volume,
    ]
    assert set(submit_headers) == {
        "x-config-filename",
        "x-atomixos-nonce",
        "x-atomixos-signature",
    }
    assert "x-atomixos-key-id" not in submit_headers
    assert set(validate_headers) == set(submit_headers)
    assert "x-atomixos-key-id" not in validate_headers
    assert "x-atomixos-poll-token" not in job_headers
    assert "x-atomixos-signature" not in job_headers
    assert submit_headers["x-config-filename"]["required"] is False
    assert submit_headers["x-atomixos-nonce"]["required"] is False
    assert submit_headers["x-atomixos-signature"]["required"] is False
    assert "provisioned-device re-apply" in submit_headers["x-atomixos-nonce"]["description"]
    assert "provisioned-device re-apply" in submit_headers["x-atomixos-signature"]["description"]
    assert validate_headers["x-config-filename"]["required"] is False
    assert validate_headers["x-atomixos-nonce"]["required"] is True
    assert validate_headers["x-atomixos-signature"]["required"] is True
    for operation in authenticated_operations:
        headers = {param["name"]: param for param in operation["parameters"]}
        assert {"x-atomixos-nonce", "x-atomixos-signature"} <= set(headers)
        assert headers["x-atomixos-nonce"]["required"] is True
        assert headers["x-atomixos-signature"]["required"] is True
    put_user_schema = put_user["requestBody"]["content"]["application/json"]["schema"]
    patch_network_schema = patch_network["requestBody"]["content"]["application/json"]["schema"]
    put_container_schema = put_container["requestBody"]["content"]["application/json"]["schema"]
    put_container_network_schema = put_container_network["requestBody"]["content"][
        "application/json"
    ]["schema"]
    put_container_volume_schema = put_container_volume["requestBody"]["content"][
        "application/json"
    ]["schema"]
    assert put_user_schema["additionalProperties"] is False
    assert patch_network_schema["additionalProperties"] is False
    assert put_container_schema["additionalProperties"] is False
    assert put_container_network_schema["additionalProperties"] is False
    assert put_container_volume_schema["additionalProperties"] is False
    assert set(put_container_schema["required"]) == {
        "privileged",
        "Container",
    }
    assert put_container_network_schema["required"] == ["Network"]
    assert put_container_volume_schema["required"] == ["Volume"]

    assert nonce["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/NonceResponseBody"
    )
    assert submit["responses"]["202"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/SubmitConfigResponseBody"
    )
    assert "application/toml" in export["responses"]["200"]["content"]
    assert validate["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/ValidationResponseBody"
    )
    assert get_job["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/JobResponseBody"
    )
    auth_error_ref = submit["responses"]["401"]["content"]["application/json"]["schema"]["$ref"]
    submit_400_ref = submit["responses"]["400"]["content"]["application/json"]["schema"]["$ref"]
    assert "FrameworkErrorResponseBody" in auth_error_ref
    submit_409_ref = submit["responses"]["409"]["content"]["application/json"]["schema"]["$ref"]
    validate_400_ref = validate["responses"]["400"]["content"]["application/json"][
        "schema"
    ]["$ref"]
    get_job_404_ref = get_job["responses"]["404"]["content"]["application/json"]["schema"]["$ref"]
    assert "ApiErrorResponseBody" in submit_400_ref
    assert "ApiErrorResponseBody" in submit_409_ref
    assert "ValidationResponseBody" in validate_400_ref
    assert "ApiErrorResponseBody" in get_job_404_ref
    job_schema = schema["components"]["schemas"]["JobResponseBody"]
    assert job_schema["properties"]["events"]["items"]["$ref"].endswith(
        "/JobEventResponseBody"
    )
    assert job_schema["properties"]["result"]["$ref"].endswith(
        "/ProvisionResultResponseBody"
    )
    location_header = submit["responses"]["202"]["headers"]["Location"]
    assert location_header["schema"] == {"type": "string"}

    assert "/" not in schema["paths"]
    assert "/apply" not in schema["paths"]
    assert "/ui/jobs/{job_id}" not in schema["paths"]
    assert "/assets/atomixos.png" not in schema["paths"]
    assert "/assets/config_dropzone.png" not in schema["paths"]

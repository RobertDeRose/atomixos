"""Tests for atomixos_provision.app routes."""

from litestar.testing import AsyncTestClient

from atomixos_provision.app import create_app


async def test_nonce_response_returns_nonce(tmp_path):
    async with AsyncTestClient(app=create_app(config_root=tmp_path)) as client:
        response = await client.get("/api/nonce")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"nonce"}
    assert len(body["nonce"]) > 20


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


async def test_validate_requires_auth_even_before_provisioning(tmp_path):
    async with AsyncTestClient(app=create_app(config_root=tmp_path)) as client:
        response = await client.post("/api/validate", content=b"version = 1\n")

    assert response.status_code == 401


async def test_boot_ui_serves_configuration_forms(tmp_path):
    async with AsyncTestClient(app=create_app(config_root=tmp_path)) as client:
        response = await client.get("/")

    assert response.status_code == 200
    body = response.text
    assert "Apply Existing Configuration" in body
    assert 'name="config_file"' in body
    assert "Generate New Configuration" not in body
    assert "Download signing challenge" not in body


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


async def test_openapi_documents_config_upload_and_auth_headers(tmp_path):
    async with AsyncTestClient(app=create_app(config_root=tmp_path)) as client:
        response = await client.get("/schema/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    submit = schema["paths"]["/api/config"]["post"]
    validate = schema["paths"]["/api/validate"]["post"]
    get_job = schema["paths"]["/api/jobs/{job_id}"]["get"]

    assert submit["requestBody"]["content"]["application/octet-stream"]["schema"] == {
        "type": "string",
        "format": "binary",
    }
    assert validate["requestBody"] == submit["requestBody"]
    submit_headers = {param["name"] for param in submit["parameters"]}
    validate_headers = {param["name"] for param in validate["parameters"]}
    job_headers = {param["name"] for param in get_job["parameters"]}
    assert "x-config-filename" in submit_headers
    assert "x-atomixos-signature" in submit_headers
    assert "x-atomixos-key-id" not in submit_headers
    assert "x-config-filename" in validate_headers
    assert "x-atomixos-signature" in validate_headers
    assert "x-atomixos-key-id" not in validate_headers
    assert "x-atomixos-poll-token" not in job_headers
    assert "x-atomixos-signature" not in job_headers
    auth_error_ref = submit["responses"]["401"]["content"]["application/json"]["schema"]["$ref"]
    assert "FrameworkErrorResponseBody" in auth_error_ref
    location_header = submit["responses"]["202"]["headers"]["Location"]
    assert location_header["schema"] == {"type": "string"}
    assert "/" not in schema["paths"]
    assert "/apply" not in schema["paths"]
    assert "/assets/atomixos.png" not in schema["paths"]

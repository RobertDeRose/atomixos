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
    assert put_user["requestBody"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/PartialUserRequestBody"
    )
    assert patch_network["requestBody"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/PartialNetworkRequestBody"
    )
    assert put_container["requestBody"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/PartialContainerRequestBody"
    )
    assert put_container_network["requestBody"]["content"]["application/json"]["schema"][
        "$ref"
    ].endswith("/PartialContainerNetworkRequestBody")
    assert put_container_volume["requestBody"]["content"]["application/json"]["schema"][
        "$ref"
    ].endswith("/PartialContainerVolumeRequestBody")
    assert set(schema["components"]["schemas"]["PartialContainerRequestBody"]["required"]) == {
        "privileged",
        "Container",
    }
    assert schema["components"]["schemas"]["PartialContainerNetworkRequestBody"]["required"] == [
        "Network"
    ]
    assert schema["components"]["schemas"]["PartialContainerVolumeRequestBody"]["required"] == [
        "Volume"
    ]

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
    assert "FrameworkErrorResponseBody" in auth_error_ref
    submit_409_ref = submit["responses"]["409"]["content"]["application/json"]["schema"]["$ref"]
    validate_400_ref = validate["responses"]["400"]["content"]["application/json"][
        "schema"
    ]["$ref"]
    get_job_404_ref = get_job["responses"]["404"]["content"]["application/json"]["schema"]["$ref"]
    assert "400" not in submit["responses"]
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
    assert "/assets/atomixos.png" not in schema["paths"]

from __future__ import annotations

import asyncio
import functools
import io
import json

import pytest
from quart import Quart
from PIL import Image
from werkzeug.datastructures import FileStorage

from private.libraries.jwt import AUD_RED_LEAF_TOWN, subject_encode
from red_leaf_town.application import GameService
from red_leaf_town.content import load_content
from red_leaf_town.infrastructure import InMemoryPlayerRepository
from red_leaf_town.runtime import set_service
from red_leaf_town.partner_content import load_partner_catalog
from red_leaf_town.story_assets import load_story_asset_catalog
from red_leaf_town.story_content import load_story_catalog
from red_leaf_town.web.routes import COOKIE_NAME, create_blueprint


def runs(function):
    @functools.wraps(function)
    def wrapper(*args, **kwargs):
        return asyncio.run(function(*args, **kwargs))

    return wrapper


WELCOME_SCRIPT = {
    "id": "welcome",
    "title": "第一次进农场",
    "trigger": {"hook": "cue", "params": {"cue": "view:farm"}},
    "steps": [
        {"type": "dialogue", "speaker": "枫糖", "text": "这块地空了一整个冬天啦。"},
    ],
}


@pytest.fixture
def story_paths(tmp_path):
    asset_path = tmp_path / "story_assets.json"
    asset_path.write_text(json.dumps({"schema_version": 1, "assets": []}), encoding="utf-8")
    script_dir = tmp_path / "story"
    script_dir.mkdir()
    (script_dir / "welcome.json").write_text(json.dumps(WELCOME_SCRIPT), encoding="utf-8")
    partner_path = tmp_path / "partners.json"
    load_story_asset_catalog.cache_clear()
    load_story_catalog.cache_clear()
    yield asset_path, script_dir, partner_path
    load_story_asset_catalog.cache_clear()
    load_story_catalog.cache_clear()


@pytest.fixture
def client(story_paths, monkeypatch):
    asset_path, script_dir, partner_path = story_paths
    monkeypatch.setenv("RED_LEAF_TOWN_ADMIN_TOKEN", "test-admin-token")
    content = load_content()
    service = GameService(
        content,
        InMemoryPlayerRepository(content),
        clock=lambda: 1_700_000_000,
        partner_catalog_loader=lambda: load_partner_catalog(partner_path),
        story_catalog_loader=lambda: load_story_catalog(script_dir, asset_path, partner_path),
        story_asset_loader=lambda: load_story_asset_catalog(asset_path),
    )
    service.ensure_player("story-sub", "小枫")
    set_service(service)
    app = Quart(__name__)
    app.register_blueprint(create_blueprint(
        partner_catalog_path=partner_path,
        story_asset_path=asset_path,
        story_script_dir=script_dir,
    ))
    yield app.test_client()
    set_service(None)


def authenticate(client, sub="story-sub"):
    client.set_cookie("localhost", COOKIE_NAME, subject_encode(sub, AUD_RED_LEAF_TOWN))


def admin_headers():
    return {"X-Admin-Token": "test-admin-token"}


@runs
async def test_cue_requires_login(client):
    response = await client.post("/api/red-leaf-town/story/cue", json={"cue": "view:farm"})
    assert response.status_code == 401


@runs
async def test_cue_returns_story_then_stops_after_seen(client):
    authenticate(client)
    response = await client.post("/api/red-leaf-town/story/cue", json={"cue": "view:farm"})
    body = await response.get_json()
    assert response.status_code == 200
    assert [entry["id"] for entry in body["data"]["stories"]] == ["welcome"]
    assert body["data"]["stories"][0]["mode"] == "inline"

    seen = await client.post("/api/red-leaf-town/story/welcome/seen")
    assert seen.status_code == 200
    assert (await seen.get_json())["data"]["result"]["story_id"] == "welcome"

    again = await client.post("/api/red-leaf-town/story/cue", json={"cue": "view:farm"})
    assert (await again.get_json())["data"]["stories"] == []


@runs
async def test_cue_ignores_unrelated_signal(client):
    authenticate(client)
    response = await client.post("/api/red-leaf-town/story/cue", json={"cue": "view:mining"})
    assert (await response.get_json())["data"]["stories"] == []


@runs
async def test_malformed_cue_is_rejected(client):
    authenticate(client)
    response = await client.post("/api/red-leaf-town/story/cue", json={"cue": "VIEW FARM"})
    assert response.status_code == 400
    assert (await response.get_json())["code"] == "invalid_story_cue"


@runs
async def test_unknown_story_seen_returns_404(client):
    authenticate(client)
    response = await client.post("/api/red-leaf-town/story/nope/seen")
    assert response.status_code == 404


@runs
async def test_admin_story_payload_requires_token(client):
    response = await client.get("/api/red-leaf-town/admin/story")
    assert response.status_code == 403


@runs
async def test_admin_story_payload_lists_scripts(client):
    response = await client.get("/api/red-leaf-town/admin/story", headers=admin_headers())
    body = await response.get_json()
    assert response.status_code == 200
    assert [entry["id"] for entry in body["data"]["scripts"]] == ["welcome"]
    assert body["data"]["assets"] == []
    assert [entry["id"] for entry in body["data"]["options"]["kinds"]] == ["background", "portrait"]
    assert "blends" not in body["data"]["options"]
    assert "cue" in body["data"]["options"]["trigger_hooks"]


def png_bytes(size, color="#a04030", mode="RGB"):
    image = io.BytesIO()
    Image.new(mode, size, color).save(image, format="PNG")
    return image.getvalue()


@runs
async def test_story_asset_upload_transcodes_and_registers(client, monkeypatch):
    from src.libraries import cdn_client

    uploaded = {}
    monkeypatch.setattr(cdn_client, "upload_bytes_at", lambda path, data, content_type: uploaded.update(
        path=path, data=data, content_type=content_type) or True)
    monkeypatch.setattr(cdn_client, "cdn_url_at", lambda path: f"https://cdn.example/{path}")

    response = await client.post(
        "/api/red-leaf-town/admin/story/assets",
        files={"file": FileStorage(stream=io.BytesIO(png_bytes((3200, 1800))), filename="gate.png", content_type="image/png")},
        form={"id": "autumn_gate", "name": "镇口", "kind": "background"},
        headers=admin_headers(),
    )
    body = await response.get_json()
    assert response.status_code == 201
    assert uploaded["path"].startswith("red-leaf-town/story/background/autumn_gate-")
    assert uploaded["content_type"] == "image/webp"
    with Image.open(io.BytesIO(uploaded["data"])) as converted:
        assert converted.format == "WEBP"
        assert converted.size == (2560, 1440)
    assert body["data"]["width"] == 2560
    assert body["data"]["url"].startswith("https://cdn.example/")

    listed = await client.get("/api/red-leaf-town/admin/story", headers=admin_headers())
    assert [entry["id"] for entry in (await listed.get_json())["data"]["assets"]] == ["autumn_gate"]


@runs
async def test_portrait_upload_keeps_alpha(client, monkeypatch):
    from src.libraries import cdn_client

    uploaded = {}
    monkeypatch.setattr(cdn_client, "upload_bytes_at", lambda path, data, content_type: uploaded.update(data=data) or True)
    monkeypatch.setattr(cdn_client, "cdn_url_at", lambda path: f"https://cdn.example/{path}")

    response = await client.post(
        "/api/red-leaf-town/admin/story/assets",
        files={"file": FileStorage(
            stream=io.BytesIO(png_bytes((900, 1600), color=(160, 64, 48, 128), mode="RGBA")),
            filename="maple.png",
            content_type="image/png",
        )},
        form={"id": "maple_smile", "name": "枫糖 微笑", "kind": "portrait"},
        headers=admin_headers(),
    )
    assert response.status_code == 201
    with Image.open(io.BytesIO(uploaded["data"])) as converted:
        assert converted.mode in ("RGBA", "RGBa")


@runs
async def test_asset_id_must_be_a_slug(client, monkeypatch):
    from src.libraries import cdn_client

    monkeypatch.setattr(cdn_client, "upload_bytes_at", lambda path, data, content_type: True)
    response = await client.post(
        "/api/red-leaf-town/admin/story/assets",
        files={"file": FileStorage(stream=io.BytesIO(png_bytes((640, 360))), filename="gate.png", content_type="image/png")},
        form={"id": "Autumn Gate", "name": "镇口", "kind": "background"},
        headers=admin_headers(),
    )
    assert response.status_code == 400
    assert (await response.get_json())["code"] == "invalid_asset"


@runs
async def test_portrait_layout_is_saved_on_the_asset(client, monkeypatch):
    from src.libraries import cdn_client

    monkeypatch.setattr(cdn_client, "upload_bytes_at", lambda path, data, content_type: True)
    monkeypatch.setattr(cdn_client, "cdn_url_at", lambda path: f"https://cdn.example/{path}")
    await client.post(
        "/api/red-leaf-town/admin/story/assets",
        files={"file": FileStorage(stream=io.BytesIO(png_bytes((900, 1600))), filename="maple.png", content_type="image/png")},
        form={"id": "maple_smile", "name": "枫糖", "kind": "portrait"},
        headers=admin_headers(),
    )

    updated = await client.patch(
        "/api/red-leaf-town/admin/story/assets/maple_smile",
        json={
            "inline_layout": {"scale": 1.35, "offset_x": -0.12, "offset_y": 0.06},
            "stage_layout": {"scale": 3.2, "offset_x": 0, "offset_y": 0},
        },
        headers=admin_headers(),
    )
    body = await updated.get_json()
    assert updated.status_code == 200
    assert body["data"]["inline_layout"] == {"scale": 1.35, "offset_x": -0.12, "offset_y": 0.06}
    assert body["data"]["stage_layout"]["scale"] == 3.2

    listed = await client.get("/api/red-leaf-town/admin/story", headers=admin_headers())
    assert (await listed.get_json())["data"]["assets"][0]["inline_layout"]["scale"] == 1.35

    rejected = await client.patch(
        "/api/red-leaf-town/admin/story/assets/maple_smile",
        json={"inline_layout": {"scale": 5}},
        headers=admin_headers(),
    )
    assert rejected.status_code == 400

    missing = await client.patch(
        "/api/red-leaf-town/admin/story/assets/nope",
        json={"scale": 1.2},
        headers=admin_headers(),
    )
    assert missing.status_code == 404


@runs
async def test_asset_delete_blocked_while_referenced(client, monkeypatch, story_paths):
    from src.libraries import cdn_client

    asset_path, script_dir, _ = story_paths
    monkeypatch.setattr(cdn_client, "upload_bytes_at", lambda path, data, content_type: True)
    monkeypatch.setattr(cdn_client, "cdn_url_at", lambda path: f"https://cdn.example/{path}")
    await client.post(
        "/api/red-leaf-town/admin/story/assets",
        files={"file": FileStorage(stream=io.BytesIO(png_bytes((640, 360))), filename="gate.png", content_type="image/png")},
        form={"id": "autumn_gate", "name": "镇口", "kind": "background"},
        headers=admin_headers(),
    )
    (script_dir / "opening.json").write_text(json.dumps({
        "id": "opening",
        "title": "抵达红叶镇",
        "trigger": {"hook": "player_level", "params": {"level": 2}},
        "steps": [
            {"type": "background", "asset_id": "autumn_gate"},
            {"type": "dialogue", "speaker": "枫糖", "text": "欢迎来到红叶镇。"},
        ],
    }), encoding="utf-8")
    reloaded = await client.post("/api/red-leaf-town/admin/story/reload", headers=admin_headers())
    assert (await reloaded.get_json())["data"]["script_count"] == 2

    blocked = await client.delete("/api/red-leaf-town/admin/story/assets/autumn_gate", headers=admin_headers())
    assert blocked.status_code == 409

    (script_dir / "opening.json").unlink()
    await client.post("/api/red-leaf-town/admin/story/reload", headers=admin_headers())
    removed = await client.delete("/api/red-leaf-town/admin/story/assets/autumn_gate", headers=admin_headers())
    assert removed.status_code == 200


@runs
async def test_broken_script_reports_invalid_content(client, story_paths):
    _, script_dir, _ = story_paths
    (script_dir / "broken.json").write_text(json.dumps({
        "id": "broken",
        "title": "坏剧本",
        "trigger": {"hook": "cue", "params": {"cue": "view:farm"}},
        "steps": [{"type": "background", "asset_id": "missing_asset"}, {"type": "dialogue", "text": "……"}],
    }), encoding="utf-8")
    await client.post("/api/red-leaf-town/admin/story/reload", headers=admin_headers())
    response = await client.get("/api/red-leaf-town/admin/story", headers=admin_headers())
    assert response.status_code == 400
    assert (await response.get_json())["code"] == "invalid_story_content"

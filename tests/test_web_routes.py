from __future__ import annotations

import asyncio
import functools
import io

import pytest
from quart import Quart
from PIL import Image
from werkzeug.datastructures import FileStorage

from private.libraries.jwt import AUD_RED_LEAF_TOWN, subject_encode
from red_leaf_town.application import GameService
from red_leaf_town.content import load_content
from red_leaf_town.domain import QQIdentity
from red_leaf_town.infrastructure import InMemoryPlayerRepository
from red_leaf_town.runtime import set_service
from red_leaf_town.partner_content import load_partner_catalog
from red_leaf_town.web.routes import COOKIE_NAME, create_blueprint


def runs(function):
    @functools.wraps(function)
    def wrapper(*args, **kwargs):
        return asyncio.run(function(*args, **kwargs))

    return wrapper


@pytest.fixture
def service():
    content = load_content()
    game = GameService(content, InMemoryPlayerRepository(content), clock=lambda: 1_700_000_000)
    game.ensure_player("route-sub", "小枫")
    set_service(game)
    yield game
    set_service(None)


@pytest.fixture
def client(service):
    app = Quart(__name__)
    app.register_blueprint(create_blueprint())
    return app.test_client()


def authenticate(client, sub="route-sub"):
    client.set_cookie("localhost", COOKIE_NAME, subject_encode(sub, AUD_RED_LEAF_TOWN))


def valid_partner_payload():
    return {
        "id": "maple_sprite",
        "name": "枫糖",
        "rarity": 4,
        "description": "擅长农作的伙伴",
        "growth_curve": "linear",
        "tendencies": [{"industry": "farming", "level_1": 16, "level_60": 92}],
        "trait_codes": ["1", "2"],
        "artworks": [],
        "avatar_crop": {"source_breakthrough": 0, "x": 0, "y": 0, "w": 100, "h": 100},
    }


@pytest.fixture
def admin_client(service, tmp_path, monkeypatch):
    monkeypatch.setenv("RED_LEAF_TOWN_ADMIN_TOKEN", "test-admin-token")
    catalog_path = tmp_path / "partners.json"
    content_path = tmp_path / "game.json"
    content_path.write_text(f"{load_content().model_dump_json(indent=2)}\n", encoding="utf-8")
    service.partner_catalog_loader = lambda: load_partner_catalog(catalog_path)
    app = Quart(f"{__name__}.admin")
    app.register_blueprint(create_blueprint(game_content_path=content_path, partner_catalog_path=catalog_path))
    return app.test_client()


def admin_headers():
    return {"X-Admin-Token": "test-admin-token"}


@runs
async def test_state_requires_login(client):
    response = await client.get("/api/red-leaf-town/state")
    assert response.status_code == 401
    assert (await response.get_json())["code"] == "unauthorized"


@runs
async def test_shop_and_plant_api(client):
    authenticate(client)
    bought = await client.post("/api/red-leaf-town/shop/buy", json={"shop_id": "carrot_seed", "quantity": 2})
    assert bought.status_code == 200
    assert (await bought.get_json())["data"]["state"]["player"]["coins"] == 60

    planted = await client.post("/api/red-leaf-town/plots/0/plant", json={"crop_id": "carrot"})
    body = await planted.get_json()
    assert planted.status_code == 200
    assert body["data"]["state"]["plots"][0]["crop_id"] == "carrot"
    assert len(body["data"]["state"]["plots"][0]["task_snapshot"]["quality_parameters"]["probabilities"]) == 5


@runs
async def test_gacha_and_partner_growth_apis_commit_domain_actions(client, service):
    from red_leaf_town.domain.economy import add_item

    player = service.repository.get_by_sub("route-sub")

    def prepare(state):
        state.experience = service.content.levels[-1].total_xp
        add_item(state, next(iter(service.content.partner_growth.experience_books)), 1)

    service.repository.update(player.player_id, prepare)
    service.admin_grant_partner(player.player_id, "xiang_hanyang")
    authenticate(client)

    pulled = await client.post(
        "/api/red-leaf-town/gacha/pull",
        json={"count": 10, "request_id": "route-recruit-request", "pool_id": "standard-1"},
    )
    replayed = await client.post(
        "/api/red-leaf-town/gacha/pull",
        json={"count": 10, "request_id": "route-recruit-request", "pool_id": "standard-1"},
    )
    pulled_body = (await pulled.get_json())["data"]
    replayed_body = (await replayed.get_json())["data"]

    assert pulled.status_code == replayed.status_code == 200
    assert replayed_body["result"]["replayed"] is True
    assert pulled_body["result"]["results"] == replayed_body["result"]["results"]

    book_id = next(iter(service.content.partner_growth.experience_books))
    trained = await client.post(
        "/api/red-leaf-town/partners/xiang_hanyang/train",
        json={"item_id": book_id, "quantity": 1},
    )
    assert trained.status_code == 200
    assert (await trained.get_json())["data"]["result"]["level"] > 1


@runs
async def test_state_lists_story_crop_without_putting_its_seed_in_shop(client):
    authenticate(client)
    response = await client.get("/api/red-leaf-town/state")
    state = (await response.get_json())["data"]

    assert "orange_berry" in {crop["id"] for crop in state["crops"]}
    assert "orange_berry_seed" not in {entry["item_id"] for entry in state["shop"]}


@runs
async def test_sell_api_accepts_exact_quality_bucket(client, service):
    from red_leaf_town.domain.economy import add_item

    player = service.repository.get_by_sub("route-sub")
    service.repository.update(player.player_id, lambda state: add_item(state, "carrot", 2, 3))
    authenticate(client)
    response = await client.post(
        "/api/red-leaf-town/inventory/carrot/sell",
        json={"quantity": 1, "quality": 3},
    )
    body = await response.get_json()
    assert response.status_code == 200
    assert body["data"]["result"]["quality_name"] == "上品"
    assert body["data"]["result"]["unit_price"] == 15


@runs
async def test_gathering_partner_start_and_talent_apis(client, service):
    player = service.repository.get_by_sub("route-sub")
    service.admin_grant_partner(player.player_id, "fein")
    authenticate(client)

    assigned = await client.put(
        "/api/red-leaf-town/gathering/sites/maple_forest/partner",
        json={"partner_id": "fein"},
    )
    assert assigned.status_code == 200
    assert (await assigned.get_json())["data"]["state"]["gathering_sites"][0]["assigned_partner_ids"] == ["fein"]

    started = await client.post(
        "/api/red-leaf-town/gathering/sites/maple_forest/start",
        json={"task_id": "collect_maple_wood"},
    )
    body = await started.get_json()
    assert started.status_code == 200
    assert body["data"]["state"]["gathering_sites"][0]["task_snapshot"]["industry"] == "gathering"
    assert body["data"]["state"]["partners"][0]["locked"] is True

    def finish_gathering(state):
        task = state.gathering_sites[0].task_snapshot
        task.started_at = 1_700_000_000 - task.final_duration
        task.ready_at = 1_700_000_000

    service.repository.update(player.player_id, finish_gathering)
    ready_response = await client.get("/api/red-leaf-town/state")
    ready_site = (await ready_response.get_json())["data"]["gathering_sites"][0]
    pool_ids = {"maple_wood", "woodland_mushroom", "maple_resin", "amber_beeswax"}
    assert ready_site["task_results"]
    assert {result["item_id"] for result in ready_site["task_results"]} <= pool_ids

    collected = await client.post("/api/red-leaf-town/gathering/sites/maple_forest/collect")
    collected_body = await collected.get_json()
    assert collected.status_code == 200
    assert {drop["item_id"] for drop in collected_body["data"]["result"]["drops"]} <= pool_ids
    assert collected_body["data"]["state"]["gathering_sites"][0]["task_results"] == []

    service.repository.update(player.player_id, lambda state: setattr(state, "experience", 20))
    unlocked = await client.post("/api/red-leaf-town/talents/gathering_roster_1/unlock")
    unlocked_body = await unlocked.get_json()
    assert unlocked.status_code == 200
    assert unlocked_body["data"]["state"]["industry_rules"]["gathering"]["partner_capacity"] == 2


@runs
async def test_crafting_recipe_hook_and_start_api(client, service):
    from red_leaf_town.domain.economy import add_item

    player = service.repository.get_by_sub("route-sub")
    service.repository.update(player.player_id, lambda state: setattr(state, "experience", 60))
    service.repository.update(player.player_id, lambda state: add_item(state, "maple_wood", 2, 1))
    authenticate(client)

    state_response = await client.get("/api/red-leaf-town/state")
    station = (await state_response.get_json())["data"]["crafting_stations"][0]
    recipe = next(entry for entry in station["recipes"] if entry["id"] == "saw_maple_plank")
    assert recipe["unlocked"] is True
    assert recipe["unlock_condition"]["hook"] == "player_level"

    locked = await client.post(
        "/api/red-leaf-town/crafting/stations/town_workbench/start",
        json={"recipe_id": "pickle_carrot"},
    )
    assert locked.status_code == 409
    assert (await locked.get_json())["code"] == "recipe_locked"

    started = await client.post(
        "/api/red-leaf-town/crafting/stations/town_workbench/start",
        json={"recipe_id": "saw_maple_plank"},
    )
    body = await started.get_json()
    assert started.status_code == 200
    assert body["data"]["state"]["crafting_stations"][0]["task_snapshot"]["industry"] == "crafting"
    assert body["data"]["result"]["consumed_inputs"] == [
        {"item_id": "maple_wood", "quality": 1, "quantity": 2},
    ]


@runs
async def test_mining_start_api_allows_player_without_partner(client, service):
    player = service.repository.get_by_sub("route-sub")
    service.repository.update(player.player_id, lambda state: setattr(state, "experience", 20))
    authenticate(client)

    started = await client.post(
        "/api/red-leaf-town/mining/sites/copper_foothill/start",
        json={"task_id": "mine_red_copper"},
    )
    body = await started.get_json()
    assert started.status_code == 200
    site = body["data"]["state"]["mining_sites"][0]
    assert site["task_snapshot"]["industry"] == "mining"
    assert site["task_snapshot"]["assigned_partner_ids"] == []


@runs
async def test_invalid_action_returns_structured_error(client):
    authenticate(client)
    response = await client.post("/api/red-leaf-town/plots/0/plant", json={"crop_id": "carrot"})
    assert response.status_code == 400
    body = await response.get_json()
    assert body == {"code": "resource_insufficient", "message": "物品数量不足"}


@runs
async def test_binding_code_api(client):
    authenticate(client)
    response = await client.post("/api/red-leaf-town/account/binding-code")
    body = await response.get_json()
    assert response.status_code == 200
    assert body["data"]["command"].startswith("绑定红叶镇 ")
    assert body["data"]["expires_in"] == 600


@runs
async def test_oauth_callback_creates_one_player_and_sets_isolated_cookie(client, service, monkeypatch):
    import private.libraries.df_oauth as oauth

    async def complete_login(code, state):
        return {
            "app": "red_leaf_town",
            "sub": "new-oauth-sub",
            "username": "maple",
            "nickname": "红枫",
            "next": "/red-leaf-town/",
        }

    monkeypatch.setattr(oauth, "complete_login", complete_login)
    response = await client.get("/api/oauth/red-leaf-town/callback?code=code&state=state")
    assert response.status_code == 302
    assert response.headers["Location"] == "/red-leaf-town/"
    assert COOKIE_NAME in response.headers.get("Set-Cookie", "")
    first = service.repository.get_by_sub("new-oauth-sub")
    assert first and first.display_name == "红枫"

    await client.get("/api/oauth/red-leaf-town/callback?code=code&state=state")
    second = service.repository.get_by_sub("new-oauth-sub")
    assert second.player_id == first.player_id


@runs
async def test_partner_admin_requires_token(admin_client):
    response = await admin_client.get("/api/red-leaf-town/admin/partners")
    assert response.status_code == 403
    assert (await response.get_json())["code"] == "forbidden"


@runs
async def test_crop_admin_updates_content_and_live_service(admin_client, service):
    forbidden = await admin_client.get("/api/red-leaf-town/admin/crops")
    assert forbidden.status_code == 403

    listed = await admin_client.get("/api/red-leaf-town/admin/crops", headers=admin_headers())
    payload = (await listed.get_json())["data"]
    carrot = next(crop for crop in payload["crops"] if crop["id"] == "carrot")
    tutorial = next(crop for crop in payload["crops"] if crop["id"] == "orange_berry")
    assert carrot["chart_enabled"] is True
    assert tutorial["seed_price"] is None

    updated = await admin_client.put(
        "/api/red-leaf-town/admin/crops",
        json={"crops": [{
            "id": "carrot",
            "seed_price": 9,
            "produce_sell_price": 11,
            "growth_seconds": 7200,
            "quality": {
                "thresholds": [5, 25, 45, 160],
                "width": 10,
                "miracle_probability_cap": 0.002,
                "miracle_eligible": True,
            },
        }]},
        headers=admin_headers(),
    )
    assert updated.status_code == 200
    assert service.content.crop_map["carrot"].growth_seconds == 7200
    assert service.content.item_map["carrot"].sell_price == 11
    assert service.content.shop_map["carrot_seed"].price == 9

    invalid = await admin_client.put(
        "/api/red-leaf-town/admin/crops",
        json={"crops": [{"id": "carrot", "quality": {"thresholds": [5, 5, 45, 160], "width": 10}}]},
        headers=admin_headers(),
    )
    assert invalid.status_code == 400
    assert (await invalid.get_json())["code"] == "invalid_crop_balance"


@runs
async def test_partner_admin_crud(admin_client):
    created = await admin_client.post(
        "/api/red-leaf-town/admin/partners",
        json=valid_partner_payload(),
        headers=admin_headers(),
    )
    assert created.status_code == 201
    assert (await created.get_json())["data"]["complete"] is False

    duplicate = await admin_client.post(
        "/api/red-leaf-town/admin/partners",
        json=valid_partner_payload(),
        headers=admin_headers(),
    )
    assert duplicate.status_code == 409

    payload = valid_partner_payload()
    payload["name"] = "枫糖糖"
    payload["growth_curve"] = "late"
    updated = await admin_client.put(
        "/api/red-leaf-town/admin/partners/maple_sprite",
        json=payload,
        headers=admin_headers(),
    )
    assert updated.status_code == 200

    listed = await admin_client.get("/api/red-leaf-town/admin/partners", headers=admin_headers())
    body = await listed.get_json()
    assert body["data"]["partners"][0]["name"] == "枫糖糖"
    assert body["data"]["options"]["breakthrough_level_caps"] == [20, 40, 60]
    assert "configured" in body["data"]["options"]["cdn"]
    assert [trait["code"] for trait in body["data"]["options"]["traits"][:4]] == ["1", "2", "3", "4"]

    deleted = await admin_client.delete(
        "/api/red-leaf-town/admin/partners/maple_sprite",
        headers=admin_headers(),
    )
    assert deleted.status_code == 200


@runs
async def test_admin_searches_player_and_grants_partner_once(admin_client):
    created = await admin_client.post(
        "/api/red-leaf-town/admin/partners",
        json=valid_partner_payload(),
        headers=admin_headers(),
    )
    assert created.status_code == 201

    searched = await admin_client.get(
        "/api/red-leaf-town/admin/players",
        query_string={"q": "小枫"},
        headers=admin_headers(),
    )
    player = (await searched.get_json())["data"][0]
    assert player["owned_partner_ids"] == []

    granted = await admin_client.post(
        f"/api/red-leaf-town/admin/players/{player['player_id']}/partners",
        json={"partner_id": "maple_sprite"},
        headers=admin_headers(),
    )
    assert granted.status_code == 200
    assert (await granted.get_json())["data"]["player"]["owned_partner_ids"] == ["maple_sprite"]

    duplicate = await admin_client.post(
        f"/api/red-leaf-town/admin/players/{player['player_id']}/partners",
        json={"partner_id": "maple_sprite"},
        headers=admin_headers(),
    )
    assert duplicate.status_code == 409

    authenticate(admin_client)
    assigned = await admin_client.put(
        "/api/red-leaf-town/plots/0/partners",
        json={"partner_id": "maple_sprite"},
    )
    assert assigned.status_code == 200
    assert (await assigned.get_json())["data"]["state"]["plots"][0]["assigned_partner_ids"] == ["maple_sprite"]

    await admin_client.post(
        "/api/red-leaf-town/shop/buy",
        json={"shop_id": "carrot_seed", "quantity": 1},
    )
    planted = await admin_client.post(
        "/api/red-leaf-town/plots/0/plant",
        json={"crop_id": "carrot"},
    )
    task = (await planted.get_json())["data"]["state"]["plots"][0]["task_snapshot"]
    assert task["assigned_partner_ids"] == ["maple_sprite"]
    assert task["final_duration"] < task["base_duration"]

    locked = await admin_client.put(
        "/api/red-leaf-town/plots/0/partners",
        json={"partner_id": ""},
    )
    assert locked.status_code == 409
    assert (await locked.get_json())["code"] == "partner_assignment_locked"

    state = await admin_client.get("/api/red-leaf-town/state")
    partner = (await state.get_json())["data"]["partners"][0]
    assert partner["partner_id"] == "maple_sprite"
    assert partner["upgrade_available"] is (partner["level"] < partner["level_cap"])


@runs
async def test_partner_artwork_uploads_through_cdn_provider(admin_client, monkeypatch):
    from src.libraries import cdn_client

    await admin_client.post(
        "/api/red-leaf-town/admin/partners",
        json=valid_partner_payload(),
        headers=admin_headers(),
    )
    uploaded = {}

    def upload_bytes_at(path, data, content_type):
        uploaded.update(path=path, data=data, content_type=content_type)
        return True

    monkeypatch.setattr(cdn_client, "upload_bytes_at", upload_bytes_at)
    monkeypatch.setattr(cdn_client, "cdn_url_at", lambda path: f"https://cdn.example/{path}")

    image = io.BytesIO()
    Image.new("RGB", (1200, 1600), "#a04030").save(image, format="PNG")
    response = await admin_client.post(
        "/api/red-leaf-town/admin/partners/maple_sprite/artworks/0",
        files={"file": FileStorage(stream=io.BytesIO(image.getvalue()), filename="portrait.png", content_type="image/png")},
        form={"x": "150", "y": "0", "w": "900", "h": "1600"},
        headers=admin_headers(),
    )
    body = await response.get_json()
    assert response.status_code == 200
    assert uploaded["path"].startswith("red-leaf-town/partners/maple_sprite/breakthrough-0-")
    assert uploaded["path"].endswith(".webp")
    assert uploaded["content_type"] == "image/webp"
    with Image.open(io.BytesIO(uploaded["data"])) as converted:
        assert converted.format == "WEBP"
        assert converted.size == (900, 1600)
    assert body["data"]["artworks"][0]["url"].startswith("https://cdn.example/")
    assert body["data"]["artworks"][0]["content_type"] == "image/webp"
    assert body["data"]["avatar_crops"] == [
        {"breakthrough": 0, "x": 0, "y": 350, "w": 900, "h": 900},
        {"breakthrough": 1, "x": 0, "y": 0, "w": 1, "h": 1},
        {"breakthrough": 2, "x": 0, "y": 0, "w": 1, "h": 1},
    ]


@runs
async def test_partner_artwork_center_crops_non_nine_sixteen_image(admin_client, monkeypatch):
    from src.libraries import cdn_client

    await admin_client.post(
        "/api/red-leaf-town/admin/partners",
        json=valid_partner_payload(),
        headers=admin_headers(),
    )
    uploaded = {}
    monkeypatch.setattr(
        cdn_client,
        "upload_bytes_at",
        lambda path, data, content_type: uploaded.update(path=path, data=data, content_type=content_type) or True,
    )
    monkeypatch.setattr(cdn_client, "cdn_url_at", lambda path: f"https://cdn.example/{path}")
    image = io.BytesIO()
    Image.new("RGB", (2000, 2000), "white").save(image, format="PNG")
    response = await admin_client.post(
        "/api/red-leaf-town/admin/partners/maple_sprite/artworks/0",
        files={"file": FileStorage(stream=io.BytesIO(image.getvalue()), filename="square.png", content_type="image/png")},
        headers=admin_headers(),
    )
    assert response.status_code == 200
    with Image.open(io.BytesIO(uploaded["data"])) as converted:
        assert converted.size == (1080, 1920)


@runs
async def test_partner_artwork_rejects_invalid_manual_crop_before_upload(admin_client, monkeypatch):
    from src.libraries import cdn_client

    await admin_client.post(
        "/api/red-leaf-town/admin/partners",
        json=valid_partner_payload(),
        headers=admin_headers(),
    )
    monkeypatch.setattr(cdn_client, "upload_bytes_at", lambda *args: pytest.fail("invalid crop must not upload"))
    image = io.BytesIO()
    Image.new("RGB", (1000, 1000), "white").save(image, format="PNG")
    response = await admin_client.post(
        "/api/red-leaf-town/admin/partners/maple_sprite/artworks/0",
        files={"file": FileStorage(stream=io.BytesIO(image.getvalue()), filename="square.png", content_type="image/png")},
        form={"x": "0", "y": "0", "w": "100", "h": "100"},
        headers=admin_headers(),
    )
    assert response.status_code == 400
    assert (await response.get_json())["code"] == "invalid_artwork_crop"


@runs
async def test_admin_can_delete_a_player(admin_client, service):
    player = service.repository.get_by_sub("route-sub")
    code = service.create_binding_code("route-sub")
    identity = QQIdentity(platform="onebot", bot_id="bot-1", subject="qq-1")
    service.bind_identity(code, identity)

    response = await admin_client.delete(
        f"/api/red-leaf-town/admin/players/{player.player_id}",
        headers=admin_headers(),
    )
    body = await response.get_json()

    assert response.status_code == 200
    assert body["data"]["player"]["display_name"] == "小枫"
    assert service.repository.get(player.player_id) is None
    assert service.repository.get_by_sub("route-sub") is None
    assert service.repository.player_id_for_identity(identity) is None

    missing = await admin_client.delete(
        f"/api/red-leaf-town/admin/players/{player.player_id}",
        headers=admin_headers(),
    )
    assert missing.status_code == 404
    assert (await missing.get_json())["code"] == "player_not_found"


@runs
async def test_player_delete_requires_admin_token(admin_client, service):
    player = service.repository.get_by_sub("route-sub")
    response = await admin_client.delete(f"/api/red-leaf-town/admin/players/{player.player_id}")
    assert response.status_code == 403
    assert service.repository.get(player.player_id) is not None


@runs
async def test_deleted_player_starts_over_on_the_next_login(admin_client, service):
    player = service.repository.get_by_sub("route-sub")
    service.mark_story_seen("route-sub", "fein_farm_greeting")
    await admin_client.delete(
        f"/api/red-leaf-town/admin/players/{player.player_id}",
        headers=admin_headers(),
    )

    recreated = service.ensure_player("route-sub", "小枫")
    assert recreated.player_id != player.player_id
    assert recreated.seen_story_ids == []
    assert recreated.owned_partners == []


@runs
async def test_tribute_delivery_api(client, service):
    from red_leaf_town.domain.economy import add_item

    player = service.repository.get_by_sub("route-sub")
    service.repository.update(player.player_id, lambda state: setattr(state, "experience", 20))
    service.repository.update(player.player_id, lambda state: add_item(state, "carrot", 15))
    authenticate(client)

    response = await client.post(
        "/api/red-leaf-town/portals/first_gate/tributes/first_gate_carrot/deliver",
        json={"quantity": 15},
    )
    body = await response.get_json()

    assert response.status_code == 200
    assert body["data"]["result"]["tribute_completed"] is True
    assert body["data"]["result"]["rewards"][0]["maple_flame"] == 150
    portal = next(
        entry for entry in body["data"]["state"]["portals"] if entry["portal_id"] == "first_gate"
    )
    assert portal["completed_tribute_count"] == 1
    assert portal["completed"] is False


@runs
async def test_tribute_delivery_api_rejects_a_locked_portal(client, service):
    authenticate(client)
    response = await client.post(
        "/api/red-leaf-town/portals/first_gate/tributes/first_gate_carrot/deliver",
        json={"quantity": 1},
    )
    body = await response.get_json()

    assert response.status_code == 409
    assert body["code"] == "portal_locked"


@runs
async def test_tribute_delivery_api_requires_login(client):
    response = await client.post(
        "/api/red-leaf-town/portals/first_gate/tributes/first_gate_carrot/deliver",
        json={"quantity": 1},
    )
    assert response.status_code == 401

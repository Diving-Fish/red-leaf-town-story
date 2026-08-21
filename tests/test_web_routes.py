from __future__ import annotations

import asyncio
import functools

import pytest
from quart import Quart

from private.libraries.jwt import AUD_RED_LEAF_TOWN, subject_encode
from red_leaf_town.application import GameService
from red_leaf_town.content import load_content
from red_leaf_town.infrastructure import InMemoryPlayerRepository
from red_leaf_town.runtime import set_service
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
    assert (await bought.get_json())["data"]["state"]["player"]["coins"] == 64

    planted = await client.post("/api/red-leaf-town/plots/0/plant", json={"crop_id": "carrot"})
    body = await planted.get_json()
    assert planted.status_code == 200
    assert body["data"]["state"]["plots"][0]["crop_id"] == "carrot"


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

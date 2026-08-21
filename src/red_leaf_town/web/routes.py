from __future__ import annotations

from functools import wraps
from pathlib import Path
from urllib.parse import quote

from quart import Blueprint, jsonify, make_response, redirect, request, send_from_directory

from red_leaf_town.application import GameError
from red_leaf_town.runtime import get_service


HOME_PATH = "/red-leaf-town/"
COOKIE_NAME = "divingfish_red_leaf_town_token"
COOKIE_MAX_AGE = 86400 * 30
FRONTEND_DIST = Path(__file__).resolve().parents[3] / "frontend" / "dist"


def _safe_next(value: str) -> str:
    candidate = str(value or "").strip()
    if not candidate.startswith(HOME_PATH):
        return ""
    if candidate.startswith("//") or candidate.startswith("/\\"):
        return ""
    return candidate


def _error(message: str, status: int = 400, code: str = "request_error"):
    return jsonify({"code": code, "message": message}), status


def _oauth_error(message: str):
    return redirect(f"{HOME_PATH}?oauth_error={quote(str(message))}")


def _session_subject() -> str:
    from private.libraries.jwt import AUD_RED_LEAF_TOWN, decode

    token = request.cookies.get(COOKIE_NAME, "")
    if not token:
        return ""
    payload = decode(token, audience=AUD_RED_LEAF_TOWN)
    return str(payload.get("sub", "") or "").strip()


def login_required(handler):
    @wraps(handler)
    async def wrapped(*args, **kwargs):
        subject = _session_subject()
        if not subject:
            return _error("未登录", 401, "unauthorized")
        return await handler(subject, *args, **kwargs)

    return wrapped


def create_blueprint() -> Blueprint:
    blueprint = Blueprint("red_leaf_town", __name__)

    @blueprint.errorhandler(GameError)
    async def game_error(error: GameError):
        return _error(error.message, error.status, error.code)

    @blueprint.get("/api/red-leaf-town/health")
    async def health():
        return jsonify({"code": 0, "message": "ok"})

    @blueprint.get("/api/oauth/red-leaf-town/start")
    async def oauth_start():
        from private.libraries.df_oauth import OAuthError, build_authorize_url

        try:
            url = await build_authorize_url(
                "red_leaf_town",
                next_url=_safe_next(request.args.get("next", "")),
            )
        except OAuthError as exc:
            return _oauth_error(str(exc))
        return redirect(url)

    @blueprint.get("/api/oauth/red-leaf-town/callback")
    async def oauth_callback():
        from private.libraries.df_oauth import OAuthError, complete_login
        from private.libraries.jwt import AUD_RED_LEAF_TOWN, subject_encode

        if request.args.get("error"):
            description = request.args.get("error_description") or request.args.get("error")
            return _oauth_error(f"授权未完成：{description}")
        try:
            result = await complete_login(request.args.get("code", ""), request.args.get("state", ""))
        except OAuthError as exc:
            return _oauth_error(str(exc))
        if result.get("app") != "red_leaf_town":
            return _oauth_error("授权应用不匹配")
        subject = str(result.get("sub", "") or "").strip()
        if not subject:
            return _oauth_error("授权结果缺少账户标识")
        display_name = str(result.get("nickname") or result.get("username") or "红叶镇居民")
        get_service().ensure_player(subject, display_name)
        response = redirect(_safe_next(result.get("next", "")) or HOME_PATH)
        response.set_cookie(
            COOKIE_NAME,
            subject_encode(subject, AUD_RED_LEAF_TOWN),
            max_age=COOKIE_MAX_AGE,
            httponly=True,
            samesite="Lax",
            path="/",
        )
        return response

    @blueprint.post("/api/red-leaf-town/logout")
    async def logout():
        response = await make_response(jsonify({"code": 0, "message": "logged out"}))
        response.delete_cookie(COOKIE_NAME, path="/")
        return response

    @blueprint.get("/api/red-leaf-town/account")
    @login_required
    async def account(subject: str):
        return jsonify({"code": 0, "data": get_service().account(subject)})

    @blueprint.get("/api/red-leaf-town/state")
    @login_required
    async def state(subject: str):
        return jsonify({"code": 0, "data": get_service().snapshot_by_sub(subject)})

    @blueprint.post("/api/red-leaf-town/shop/buy")
    @login_required
    async def buy(subject: str):
        payload = await request.get_json(silent=True) or {}
        result = get_service().buy(
            subject,
            str(payload.get("shop_id", "")),
            int(payload.get("quantity", 1)),
        )
        return jsonify({"code": 0, "data": result})

    @blueprint.post("/api/red-leaf-town/plots/<int:slot>/plant")
    @login_required
    async def plant(subject: str, slot: int):
        payload = await request.get_json(silent=True) or {}
        result = get_service().plant(subject, slot, str(payload.get("crop_id", "")))
        return jsonify({"code": 0, "data": result})

    @blueprint.post("/api/red-leaf-town/plots/<int:slot>/harvest")
    @login_required
    async def harvest(subject: str, slot: int):
        result = get_service().harvest(subject, slot)
        return jsonify({"code": 0, "data": result})

    @blueprint.post("/api/red-leaf-town/inventory/<string:item_id>/sell")
    @login_required
    async def sell(subject: str, item_id: str):
        payload = await request.get_json(silent=True) or {}
        result = get_service().sell(subject, item_id, int(payload.get("quantity", 1)))
        return jsonify({"code": 0, "data": result})

    @blueprint.post("/api/red-leaf-town/account/binding-code")
    @login_required
    async def binding_code(subject: str):
        code = get_service().create_binding_code(subject)
        return jsonify({
            "code": 0,
            "data": {
                "binding_code": code,
                "command": f"绑定红叶镇 {code}",
                "expires_in": 600,
            },
        })

    @blueprint.get("/red-leaf-town/")
    @blueprint.get("/red-leaf-town/<path:asset_path>")
    async def frontend(asset_path: str = ""):
        if asset_path:
            candidate = FRONTEND_DIST / asset_path
            if candidate.is_file():
                return await send_from_directory(FRONTEND_DIST, asset_path)
        index = FRONTEND_DIST / "index.html"
        if not index.is_file():
            return _error("前端尚未构建", 503, "frontend_not_built")
        return await send_from_directory(FRONTEND_DIST, "index.html")

    return blueprint


def install(app) -> None:
    if app.extensions.get("red_leaf_town_installed"):
        return
    app.register_blueprint(create_blueprint())
    app.extensions["red_leaf_town_installed"] = True

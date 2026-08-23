from __future__ import annotations

import hashlib
import io
import os
import secrets
from functools import wraps
from pathlib import Path
from urllib.parse import quote

from quart import Blueprint, jsonify, make_response, redirect, request, send_from_directory
from pydantic import ValidationError

from red_leaf_town.application import GameError
from red_leaf_town.runtime import get_service
from red_leaf_town.partner_content import (
    BREAKTHROUGH_LEVEL_CAPS,
    DEFAULT_PARTNER_CONTENT_PATH,
    GROWTH_CURVE_NAMES,
    INDUSTRY_NAMES,
    PartnerCatalog,
    PartnerDefinition,
    PartnerArtwork,
    load_partner_catalog,
    save_partner_catalog,
)
from red_leaf_town.partner_traits import partner_trait_catalog
from red_leaf_town.story_assets import (
    DEFAULT_STORY_ASSET_PATH,
    STORY_ASSET_KIND_NAMES,
    StoryAsset,
    StoryAssetCatalog,
    load_story_asset_catalog,
    save_story_asset_catalog,
)
from red_leaf_town.story_content import DEFAULT_STORY_SCRIPT_DIR, load_story_catalog
from red_leaf_town.story_triggers import story_trigger_hook_codes


HOME_PATH = "/red-leaf-town/"
COOKIE_NAME = "divingfish_red_leaf_town_token"
COOKIE_MAX_AGE = 86400 * 30
FRONTEND_DIST = Path(__file__).resolve().parents[3] / "frontend" / "dist"
MAX_PARTNER_ARTWORK_SIZE = 12 * 1024 * 1024
MAX_PARTNER_ARTWORK_PIXELS = 60_000_000
MAX_PARTNER_ARTWORK_UNIT = 120
PARTNER_ARTWORK_INPUT_FORMATS = {"JPEG", "PNG", "WEBP"}
MAX_STORY_ASSET_SIZE = 12 * 1024 * 1024
MAX_STORY_ASSET_PIXELS = 60_000_000
MAX_STORY_ASSET_EDGE = {"background": 2560, "portrait": 1920}


def _safe_next(value: str) -> str:
    candidate = str(value or "").strip()
    if not candidate.startswith(HOME_PATH):
        return ""
    if candidate.startswith("//") or candidate.startswith("/\\"):
        return ""
    return candidate


def _error(message: str, status: int = 400, code: str = "request_error"):
    return jsonify({"code": code, "message": message}), status


def _is_admin_request() -> bool:
    expected = (
        os.environ.get("RED_LEAF_TOWN_ADMIN_TOKEN")
        or os.environ.get("AETHER_ADMIN_TOKEN")
        or "Chiyuk123456"
    ).strip()
    if not expected:
        return True
    provided = request.headers.get("X-Admin-Token", "")
    return bool(provided) and secrets.compare_digest(provided, expected)


def _admin_error():
    return _error("无权限", 403, "forbidden")


def _validation_error(error: ValidationError):
    message = "; ".join(item["msg"] for item in error.errors())
    return _error(message, 400, "invalid_partner")


def _largest_nine_sixteen_crop(width: int, height: int) -> tuple[int, int, int, int]:
    unit = min(width // 9, height // 16)
    if unit < 1:
        raise ValueError("图片尺寸太小，无法裁剪为 9:16")
    crop_width = unit * 9
    crop_height = unit * 16
    return (
        (width - crop_width) // 2,
        (height - crop_height) // 2,
        crop_width,
        crop_height,
    )


def _parse_artwork_crop(form, width: int, height: int) -> tuple[int, int, int, int]:
    values = [str(form.get(key, "")).strip() for key in ("x", "y", "w", "h")]
    if not any(values):
        return _largest_nine_sixteen_crop(width, height)
    if not all(values):
        raise ValueError("裁剪参数必须同时包含 x、y、w、h")
    try:
        x, y, crop_width, crop_height = (int(value) for value in values)
    except ValueError as exc:
        raise ValueError("裁剪参数必须是整数") from exc
    if x < 0 or y < 0 or crop_width <= 0 or crop_height <= 0:
        raise ValueError("裁剪参数超出允许范围")
    if x + crop_width > width or y + crop_height > height:
        raise ValueError("裁剪框不能超出原图边界")
    if crop_width * 16 != crop_height * 9:
        raise ValueError("插画裁剪框必须是 9:16 比例")
    return x, y, crop_width, crop_height


def _prepare_partner_artwork(data: bytes, form) -> tuple[bytes, int, int]:
    from PIL import Image, ImageOps

    with Image.open(io.BytesIO(data)) as source:
        image_format = str(source.format or "").upper()
        if image_format not in PARTNER_ARTWORK_INPUT_FORMATS:
            raise ValueError("仅支持 JPG、PNG 和 WebP 图片")
        image = ImageOps.exif_transpose(source)
        image.load()
    width, height = image.size
    if width * height > MAX_PARTNER_ARTWORK_PIXELS:
        raise ValueError("图片像素总量不能超过 6000 万")
    x, y, crop_width, crop_height = _parse_artwork_crop(form, width, height)
    image = image.crop((x, y, x + crop_width, y + crop_height))

    unit = min(crop_width // 9, MAX_PARTNER_ARTWORK_UNIT)
    output_width, output_height = unit * 9, unit * 16
    if image.size != (output_width, output_height):
        image = image.resize((output_width, output_height), Image.Resampling.LANCZOS)
    has_alpha = image.mode in {"RGBA", "LA"} or "transparency" in image.info
    image = image.convert("RGBA" if has_alpha else "RGB")
    output = io.BytesIO()
    image.save(output, format="WEBP", quality=88, method=6)
    return output.getvalue(), output_width, output_height


def _prepare_story_image(data: bytes, kind: str) -> tuple[bytes, int, int]:
    """剧情素材不裁剪，只做格式校验、长边限制和 WebP 转码，保留立绘的透明通道。"""
    from PIL import Image, ImageOps

    with Image.open(io.BytesIO(data)) as source:
        image_format = str(source.format or "").upper()
        if image_format not in PARTNER_ARTWORK_INPUT_FORMATS:
            raise ValueError("仅支持 JPG、PNG 和 WebP 图片")
        image = ImageOps.exif_transpose(source)
        image.load()
    width, height = image.size
    if width * height > MAX_STORY_ASSET_PIXELS:
        raise ValueError("图片像素总量不能超过 6000 万")
    max_edge = MAX_STORY_ASSET_EDGE[kind]
    if max(width, height) > max_edge:
        scale = max_edge / max(width, height)
        width, height = max(1, round(width * scale)), max(1, round(height * scale))
        image = image.resize((width, height), Image.Resampling.LANCZOS)
    has_alpha = image.mode in {"RGBA", "LA"} or "transparency" in image.info
    image = image.convert("RGBA" if has_alpha else "RGB")
    output = io.BytesIO()
    image.save(output, format="WEBP", quality=88, method=6)
    return output.getvalue(), width, height


def _default_avatar_crop(breakthrough: int, width: int, height: int) -> dict:
    side = min(width, height)
    return {
        "breakthrough": breakthrough,
        "x": (width - side) // 2,
        "y": (height - side) // 2,
        "w": side,
        "h": side,
    }


def _attach_cdn_urls(value):
    from src.libraries import cdn_client

    if isinstance(value, dict):
        asset_key = value.get("asset_key")
        if asset_key and "url" not in value:
            value["url"] = cdn_client.cdn_url_at(str(asset_key))
        for nested in value.values():
            _attach_cdn_urls(nested)
    elif isinstance(value, list):
        for nested in value:
            _attach_cdn_urls(nested)
    return value


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


def create_blueprint(
    *,
    partner_catalog_path: str | Path = DEFAULT_PARTNER_CONTENT_PATH,
    story_asset_path: str | Path = DEFAULT_STORY_ASSET_PATH,
    story_script_dir: str | Path = DEFAULT_STORY_SCRIPT_DIR,
) -> Blueprint:
    blueprint = Blueprint("red_leaf_town", __name__)
    catalog_path = Path(partner_catalog_path)
    story_asset_catalog_path = Path(story_asset_path)
    story_script_path = Path(story_script_dir)

    def story_catalog():
        return load_story_catalog(story_script_path, story_asset_catalog_path, catalog_path)

    def story_admin_payload() -> dict:
        from src.libraries import cdn_client

        assets = load_story_asset_catalog(story_asset_catalog_path)
        return {
            "assets": [asset.model_dump() for asset in sorted(assets.assets, key=lambda entry: entry.id)],
            "scripts": get_service().story_scripts(),
            "options": {
                "kinds": [{"id": key, "name": value} for key, value in STORY_ASSET_KIND_NAMES.items()],
                "trigger_hooks": story_trigger_hook_codes(),
                "script_directory": str(story_script_path),
                "cdn": {
                    "provider": cdn_client.active_provider(),
                    "configured": cdn_client.is_configured(),
                    "base_url": cdn_client.cdn_base_url(),
                },
            },
        }

    def serialize_partner(partner: PartnerDefinition) -> dict:
        from src.libraries import cdn_client

        data = partner.model_dump()
        for artwork in data["artworks"]:
            artwork["url"] = cdn_client.cdn_url_at(artwork["asset_key"])
        data["complete"] = partner.complete
        data["ability_preview"] = {
            tendency.industry: {
                str(level): partner.ability_at(tendency.industry, level)
                for level in (1, 20, 40, 60)
            }
            for tendency in partner.tendencies
        }
        return data

    def admin_payload(catalog: PartnerCatalog) -> dict:
        from src.libraries import cdn_client

        return {
            "partners": [serialize_partner(partner) for partner in catalog.partners],
            "options": {
                "industries": [{"id": key, "name": value} for key, value in INDUSTRY_NAMES.items()],
                "growth_curves": [{"id": key, "name": value} for key, value in GROWTH_CURVE_NAMES.items()],
                "rarities": [3, 4, 5],
                "breakthrough_level_caps": list(BREAKTHROUGH_LEVEL_CAPS),
                "cdn": {
                    "provider": cdn_client.active_provider(),
                    "configured": cdn_client.is_configured(),
                    "base_url": cdn_client.cdn_base_url(),
                },
                "traits": [
                    {
                        "code": trait.code,
                        "name": trait.name,
                        "description": trait.description,
                        "implemented": trait.implemented,
                    }
                    for trait in partner_trait_catalog()
                ],
            },
        }

    def replace_partner(catalog: PartnerCatalog, partner: PartnerDefinition) -> PartnerCatalog:
        records = [entry for entry in catalog.partners if entry.id != partner.id]
        records.append(partner)
        records.sort(key=lambda entry: entry.id)
        return PartnerCatalog(schema_version=catalog.schema_version, partners=records)

    @blueprint.errorhandler(GameError)
    async def game_error(error: GameError):
        return _error(error.message, error.status, error.code)

    @blueprint.get("/api/red-leaf-town/health")
    async def health():
        return jsonify({"code": 0, "message": "ok"})

    @blueprint.get("/api/red-leaf-town/admin/partners")
    async def admin_partner_list():
        if not _is_admin_request():
            return _admin_error()
        return jsonify({"code": 0, "data": admin_payload(load_partner_catalog(catalog_path))})

    @blueprint.post("/api/red-leaf-town/admin/partners")
    async def admin_partner_create():
        if not _is_admin_request():
            return _admin_error()
        payload = await request.get_json(silent=True) or {}
        try:
            partner = PartnerDefinition.model_validate(payload)
        except ValidationError as exc:
            return _validation_error(exc)
        catalog = load_partner_catalog(catalog_path)
        if partner.id in catalog.partner_map:
            return _error("伙伴 ID 已存在", 409, "partner_exists")
        catalog = replace_partner(catalog, partner)
        save_partner_catalog(catalog, catalog_path)
        return jsonify({"code": 0, "data": serialize_partner(partner)}), 201

    @blueprint.put("/api/red-leaf-town/admin/partners/<string:partner_id>")
    async def admin_partner_update(partner_id: str):
        if not _is_admin_request():
            return _admin_error()
        catalog = load_partner_catalog(catalog_path)
        if partner_id not in catalog.partner_map:
            return _error("伙伴不存在", 404, "partner_not_found")
        payload = await request.get_json(silent=True) or {}
        payload["id"] = partner_id
        try:
            partner = PartnerDefinition.model_validate(payload)
        except ValidationError as exc:
            return _validation_error(exc)
        catalog = replace_partner(catalog, partner)
        save_partner_catalog(catalog, catalog_path)
        return jsonify({"code": 0, "data": serialize_partner(partner)})

    @blueprint.delete("/api/red-leaf-town/admin/partners/<string:partner_id>")
    async def admin_partner_delete(partner_id: str):
        if not _is_admin_request():
            return _admin_error()
        catalog = load_partner_catalog(catalog_path)
        if partner_id not in catalog.partner_map:
            return _error("伙伴不存在", 404, "partner_not_found")
        updated = PartnerCatalog(
            schema_version=catalog.schema_version,
            partners=[partner for partner in catalog.partners if partner.id != partner_id],
        )
        save_partner_catalog(updated, catalog_path)
        return jsonify({"code": 0, "message": "已删除"})

    @blueprint.post("/api/red-leaf-town/admin/partners/<string:partner_id>/artworks/<int:breakthrough>")
    async def admin_partner_upload_artwork(partner_id: str, breakthrough: int):
        if not _is_admin_request():
            return _admin_error()
        if breakthrough not in (0, 1, 2):
            return _error("突破阶段必须是 0、1 或 2", 400, "invalid_breakthrough")
        catalog = load_partner_catalog(catalog_path)
        current = catalog.partner_map.get(partner_id)
        if current is None:
            return _error("伙伴不存在", 404, "partner_not_found")
        files = await request.files
        uploaded = files.get("file")
        if uploaded is None or not uploaded.filename:
            return _error("未选择图片", 400, "file_required")
        data = uploaded.read()
        if not data:
            return _error("图片内容为空", 400, "empty_file")
        if len(data) > MAX_PARTNER_ARTWORK_SIZE:
            return _error("图片不能超过 12 MB", 413, "file_too_large")
        try:
            form = await request.form
            webp_data, width, height = _prepare_partner_artwork(data, form)
        except ValueError as exc:
            return _error(str(exc), 400, "invalid_artwork_crop")
        except Exception:
            return _error("无法识别图片内容", 400, "invalid_image")

        content_type = "image/webp"
        digest = hashlib.sha256(webp_data).hexdigest()[:16]
        asset_key = f"red-leaf-town/partners/{partner_id}/breakthrough-{breakthrough}-{digest}.webp"
        artwork = PartnerArtwork(
            breakthrough=breakthrough,
            asset_key=asset_key,
            width=width,
            height=height,
            content_type=content_type,
        )
        payload = current.model_dump()
        payload["artworks"] = [
            entry.model_dump() for entry in current.artworks if entry.breakthrough != breakthrough
        ] + [artwork.model_dump()]
        payload["artworks"].sort(key=lambda entry: entry["breakthrough"])
        payload["avatar_crops"] = [
            entry.model_dump()
            for entry in current.avatar_crops
            if entry.breakthrough != breakthrough
        ] + [_default_avatar_crop(breakthrough, width, height)]
        payload["avatar_crops"].sort(key=lambda entry: entry["breakthrough"])
        try:
            partner = PartnerDefinition.model_validate(payload)
        except ValidationError as exc:
            return _validation_error(exc)
        from src.libraries import cdn_client

        if not cdn_client.upload_bytes_at(asset_key, webp_data, content_type):
            return _error("CDN 上传失败，请检查底层 provider 配置", 503, "cdn_upload_failed")
        save_partner_catalog(replace_partner(catalog, partner), catalog_path)
        return jsonify({"code": 0, "data": serialize_partner(partner)})

    @blueprint.get("/api/red-leaf-town/admin/story")
    async def admin_story_payload():
        if not _is_admin_request():
            return _admin_error()
        try:
            return jsonify({"code": 0, "data": _attach_cdn_urls(story_admin_payload())})
        except (ValueError, ValidationError) as exc:
            return _error(f"剧本内容无法加载：{exc}", 400, "invalid_story_content")

    @blueprint.post("/api/red-leaf-town/admin/story/reload")
    async def admin_story_reload():
        if not _is_admin_request():
            return _admin_error()
        load_story_asset_catalog.cache_clear()
        load_story_catalog.cache_clear()
        try:
            scripts = story_catalog().scripts
        except (ValueError, ValidationError) as exc:
            return _error(f"剧本内容无法加载：{exc}", 400, "invalid_story_content")
        return jsonify({"code": 0, "data": {"script_count": len(scripts)}})

    @blueprint.post("/api/red-leaf-town/admin/story/assets")
    async def admin_story_asset_upload():
        if not _is_admin_request():
            return _admin_error()
        form = await request.form
        kind = str(form.get("kind", "")).strip()
        if kind not in STORY_ASSET_KIND_NAMES:
            return _error("素材类型必须是背景或立绘", 400, "invalid_asset_kind")
        files = await request.files
        uploaded = files.get("file")
        if uploaded is None or not uploaded.filename:
            return _error("未选择图片", 400, "file_required")
        data = uploaded.read()
        if not data:
            return _error("图片内容为空", 400, "empty_file")
        if len(data) > MAX_STORY_ASSET_SIZE:
            return _error("图片不能超过 12 MB", 413, "file_too_large")
        try:
            webp_data, width, height = _prepare_story_image(data, kind)
        except ValueError as exc:
            return _error(str(exc), 400, "invalid_image")
        except Exception:
            return _error("无法识别图片内容", 400, "invalid_image")

        digest = hashlib.sha256(webp_data).hexdigest()[:16]
        asset_id = str(form.get("id", "")).strip()
        try:
            asset = StoryAsset(
                id=asset_id,
                kind=kind,
                name=str(form.get("name", "")).strip() or asset_id,
                asset_key=f"red-leaf-town/story/{kind}/{asset_id}-{digest}.webp",
                width=width,
                height=height,
                content_type="image/webp",
            )
        except ValidationError as exc:
            return _error("; ".join(item["msg"] for item in exc.errors()), 400, "invalid_asset")
        from src.libraries import cdn_client

        if not cdn_client.upload_bytes_at(asset.asset_key, webp_data, asset.content_type):
            return _error("CDN 上传失败，请检查底层 provider 配置", 503, "cdn_upload_failed")
        catalog = load_story_asset_catalog(story_asset_catalog_path)
        records = [entry for entry in catalog.assets if entry.id != asset.id]
        records.append(asset)
        save_story_asset_catalog(
            StoryAssetCatalog(schema_version=catalog.schema_version, assets=records),
            story_asset_catalog_path,
        )
        load_story_catalog.cache_clear()
        return jsonify({"code": 0, "data": _attach_cdn_urls(asset.model_dump())}), 201

    @blueprint.patch("/api/red-leaf-town/admin/story/assets/<string:asset_id>")
    async def admin_story_asset_update(asset_id: str):
        if not _is_admin_request():
            return _admin_error()
        catalog = load_story_asset_catalog(story_asset_catalog_path)
        current = catalog.asset_map.get(asset_id)
        if current is None:
            return _error("素材不存在", 404, "asset_not_found")
        body = await request.get_json(silent=True) or {}
        payload = current.model_dump()
        for field in ("name", "inline_layout", "stage_layout"):
            if field in body:
                payload[field] = body[field]
        try:
            asset = StoryAsset.model_validate(payload)
        except ValidationError as exc:
            return _error("; ".join(item["msg"] for item in exc.errors()), 400, "invalid_asset")
        save_story_asset_catalog(
            StoryAssetCatalog(
                schema_version=catalog.schema_version,
                assets=[entry for entry in catalog.assets if entry.id != asset_id] + [asset],
            ),
            story_asset_catalog_path,
        )
        load_story_catalog.cache_clear()
        return jsonify({"code": 0, "data": _attach_cdn_urls(asset.model_dump())})

    @blueprint.delete("/api/red-leaf-town/admin/story/assets/<string:asset_id>")
    async def admin_story_asset_delete(asset_id: str):
        if not _is_admin_request():
            return _admin_error()
        catalog = load_story_asset_catalog(story_asset_catalog_path)
        if asset_id not in catalog.asset_map:
            return _error("素材不存在", 404, "asset_not_found")
        try:
            users = [script.id for script in story_catalog().scripts if asset_id in script.asset_ids]
        except (ValueError, ValidationError) as exc:
            return _error(f"剧本内容无法加载：{exc}", 400, "invalid_story_content")
        if users:
            return _error(f"这张素材仍被剧本引用：{'、'.join(sorted(users))}", 409, "asset_in_use")
        save_story_asset_catalog(
            StoryAssetCatalog(
                schema_version=catalog.schema_version,
                assets=[entry for entry in catalog.assets if entry.id != asset_id],
            ),
            story_asset_catalog_path,
        )
        load_story_catalog.cache_clear()
        return jsonify({"code": 0, "message": "已删除"})

    @blueprint.get("/api/red-leaf-town/admin/players")
    async def admin_player_search():
        if not _is_admin_request():
            return _admin_error()
        try:
            limit = int(request.args.get("limit", 50))
        except (TypeError, ValueError):
            limit = 50
        players = get_service().admin_search_players(request.args.get("q", ""), limit)
        return jsonify({"code": 0, "data": players})

    @blueprint.post("/api/red-leaf-town/admin/players/<string:player_id>/partners")
    async def admin_player_grant_partner(player_id: str):
        if not _is_admin_request():
            return _admin_error()
        payload = await request.get_json(silent=True) or {}
        result = get_service().admin_grant_partner(player_id, str(payload.get("partner_id", "")))
        return jsonify({"code": 0, "data": result})

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
        return jsonify({"code": 0, "data": _attach_cdn_urls(get_service().account(subject))})

    @blueprint.get("/api/red-leaf-town/state")
    @login_required
    async def state(subject: str):
        return jsonify({"code": 0, "data": _attach_cdn_urls(get_service().snapshot_by_sub(subject))})

    @blueprint.post("/api/red-leaf-town/shop/buy")
    @login_required
    async def buy(subject: str):
        payload = await request.get_json(silent=True) or {}
        result = get_service().buy(
            subject,
            str(payload.get("shop_id", "")),
            int(payload.get("quantity", 1)),
        )
        return jsonify({"code": 0, "data": _attach_cdn_urls(result)})

    @blueprint.post("/api/red-leaf-town/plots/<int:slot>/plant")
    @login_required
    async def plant(subject: str, slot: int):
        payload = await request.get_json(silent=True) or {}
        result = get_service().plant(subject, slot, str(payload.get("crop_id", "")))
        return jsonify({"code": 0, "data": _attach_cdn_urls(result)})

    @blueprint.put("/api/red-leaf-town/plots/<int:slot>/partners")
    @login_required
    async def assign_plot_partner(subject: str, slot: int):
        payload = await request.get_json(silent=True) or {}
        result = get_service().assign_partner(subject, slot, str(payload.get("partner_id", "")))
        return jsonify({"code": 0, "data": _attach_cdn_urls(result)})

    @blueprint.post("/api/red-leaf-town/plots/<int:slot>/harvest")
    @login_required
    async def harvest(subject: str, slot: int):
        result = get_service().harvest(subject, slot)
        return jsonify({"code": 0, "data": _attach_cdn_urls(result)})

    @blueprint.put("/api/red-leaf-town/gathering/sites/<string:site_id>/partner")
    @login_required
    async def assign_gathering_partner(subject: str, site_id: str):
        payload = await request.get_json(silent=True) or {}
        result = get_service().assign_gathering_partner(
            subject,
            site_id,
            str(payload.get("partner_id", "")),
        )
        return jsonify({"code": 0, "data": _attach_cdn_urls(result)})

    @blueprint.post("/api/red-leaf-town/gathering/sites/<string:site_id>/start")
    @login_required
    async def start_gathering(subject: str, site_id: str):
        payload = await request.get_json(silent=True) or {}
        result = get_service().start_gathering(subject, site_id, str(payload.get("task_id", "")))
        return jsonify({"code": 0, "data": _attach_cdn_urls(result)})

    @blueprint.post("/api/red-leaf-town/gathering/sites/<string:site_id>/collect")
    @login_required
    async def collect_gathering(subject: str, site_id: str):
        result = get_service().collect_gathering(subject, site_id)
        return jsonify({"code": 0, "data": _attach_cdn_urls(result)})

    @blueprint.put("/api/red-leaf-town/crafting/stations/<string:station_id>/partner")
    @login_required
    async def assign_crafting_partner(subject: str, station_id: str):
        payload = await request.get_json(silent=True) or {}
        result = get_service().assign_crafting_partner(
            subject,
            station_id,
            str(payload.get("partner_id", "")),
        )
        return jsonify({"code": 0, "data": _attach_cdn_urls(result)})

    @blueprint.post("/api/red-leaf-town/crafting/stations/<string:station_id>/start")
    @login_required
    async def start_crafting(subject: str, station_id: str):
        payload = await request.get_json(silent=True) or {}
        result = get_service().start_crafting(subject, station_id, str(payload.get("recipe_id", "")))
        return jsonify({"code": 0, "data": _attach_cdn_urls(result)})

    @blueprint.post("/api/red-leaf-town/crafting/stations/<string:station_id>/collect")
    @login_required
    async def collect_crafting(subject: str, station_id: str):
        result = get_service().collect_crafting(subject, station_id)
        return jsonify({"code": 0, "data": _attach_cdn_urls(result)})

    @blueprint.put("/api/red-leaf-town/mining/sites/<string:site_id>/partner")
    @login_required
    async def assign_mining_partner(subject: str, site_id: str):
        payload = await request.get_json(silent=True) or {}
        result = get_service().assign_mining_partner(
            subject,
            site_id,
            str(payload.get("partner_id", "")),
        )
        return jsonify({"code": 0, "data": _attach_cdn_urls(result)})

    @blueprint.post("/api/red-leaf-town/mining/sites/<string:site_id>/start")
    @login_required
    async def start_mining(subject: str, site_id: str):
        payload = await request.get_json(silent=True) or {}
        result = get_service().start_mining(subject, site_id, str(payload.get("task_id", "")))
        return jsonify({"code": 0, "data": _attach_cdn_urls(result)})

    @blueprint.post("/api/red-leaf-town/mining/sites/<string:site_id>/collect")
    @login_required
    async def collect_mining(subject: str, site_id: str):
        result = get_service().collect_mining(subject, site_id)
        return jsonify({"code": 0, "data": _attach_cdn_urls(result)})

    @blueprint.post("/api/red-leaf-town/talents/<string:node_id>/unlock")
    @login_required
    async def unlock_talent(subject: str, node_id: str):
        result = get_service().unlock_talent(subject, node_id)
        return jsonify({"code": 0, "data": _attach_cdn_urls(result)})

    @blueprint.post("/api/red-leaf-town/inventory/<string:item_id>/sell")
    @login_required
    async def sell(subject: str, item_id: str):
        payload = await request.get_json(silent=True) or {}
        result = get_service().sell(
            subject,
            item_id,
            int(payload.get("quantity", 1)),
            int(payload.get("quality", 0)),
        )
        return jsonify({"code": 0, "data": _attach_cdn_urls(result)})

    @blueprint.post("/api/red-leaf-town/story/cue")
    @login_required
    async def story_cue(subject: str):
        payload = await request.get_json(silent=True) or {}
        result = get_service().story_cue(subject, str(payload.get("cue", "")))
        return jsonify({"code": 0, "data": _attach_cdn_urls(result)})

    @blueprint.post("/api/red-leaf-town/story/<string:story_id>/seen")
    @login_required
    async def story_seen(subject: str, story_id: str):
        result = get_service().mark_story_seen(subject, story_id)
        return jsonify({"code": 0, "data": _attach_cdn_urls(result)})

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

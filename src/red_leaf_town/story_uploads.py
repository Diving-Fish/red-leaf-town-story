from __future__ import annotations

import json
import secrets
import threading
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field, model_validator

from red_leaf_town.story_assets import DEFAULT_STORY_LAYOUT, StoryAssetKind, StoryAssetLayout


DEFAULT_STORY_UPLOAD_PATH = Path(__file__).resolve().parents[2] / "data" / "story_uploads.json"
# 风控：同一个上传者一小时内最多传 30 MB（按收到的原始字节算，转码前）。
UPLOAD_WINDOW_SECONDS = 3600
UPLOAD_QUOTA_BYTES = 30 * 1024 * 1024
_SAVE_LOCK = threading.Lock()


class StoryUpload(BaseModel):
    """玩家自己传的剧情素材。图只在 CDN 上，本地只留这条索引和上传者记录。"""

    id: str = Field(pattern=r"^up_[0-9a-f]{12}$")
    kind: StoryAssetKind
    name: str = Field(min_length=1, max_length=64)
    asset_key: str = Field(min_length=1)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    content_type: str = Field(pattern=r"^image/")
    uploader_sub: str = Field(min_length=1)
    uploader_name: str = Field(default="", max_length=64)
    source_bytes: int = Field(default=0, ge=0)
    created_at: int = Field(default=0, ge=0)
    # 立绘的默认站位，由上传者自己调。背景没有站位可调。
    layout: StoryAssetLayout = Field(default_factory=StoryAssetLayout)

    @model_validator(mode="after")
    def validate_layout(self):
        if self.kind == "background" and self.layout != DEFAULT_STORY_LAYOUT:
            raise ValueError("only portrait uploads carry layout parameters")
        return self


class StoryUploadIndex(BaseModel):
    schema_version: int = Field(default=1, ge=1)
    uploads: list[StoryUpload] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_ids(self):
        ids = [upload.id for upload in self.uploads]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate story upload id")
        return self

    @property
    def upload_map(self) -> dict[str, StoryUpload]:
        return {upload.id: upload for upload in self.uploads}


def new_upload_id() -> str:
    """和官方素材 ID 分开命名空间，玩家不能顶掉剧本正在用的图。"""
    return f"up_{secrets.token_hex(6)}"


def used_quota(index: StoryUploadIndex, uploader_sub: str, now: int) -> int:
    since = now - UPLOAD_WINDOW_SECONDS
    return sum(
        upload.source_bytes
        for upload in index.uploads
        if upload.uploader_sub == uploader_sub and upload.created_at > since
    )


@lru_cache(maxsize=8)
def load_story_upload_index(path: str | Path = DEFAULT_STORY_UPLOAD_PATH) -> StoryUploadIndex:
    index_path = Path(path)
    if not index_path.exists():
        return StoryUploadIndex()
    return StoryUploadIndex.model_validate(json.loads(index_path.read_text(encoding="utf-8")))


def _write(index: StoryUploadIndex, index_path: Path) -> None:
    payload = index.model_dump_json(indent=2)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = index_path.with_suffix(f"{index_path.suffix}.tmp")
    temporary.write_text(f"{payload}\n", encoding="utf-8")
    temporary.replace(index_path)
    load_story_upload_index.cache_clear()


def append_story_upload(
    upload: StoryUpload,
    path: str | Path = DEFAULT_STORY_UPLOAD_PATH,
    *,
    quota_bytes: int = UPLOAD_QUOTA_BYTES,
) -> bool:
    """追加一条上传记录。读改写整个在锁里，配额在锁内复核一次，避免并发传爆额度。"""
    index_path = Path(path)
    with _SAVE_LOCK:
        current = load_story_upload_index(index_path)
        if used_quota(current, upload.uploader_sub, upload.created_at) + upload.source_bytes > quota_bytes:
            return False
        _write(
            StoryUploadIndex(
                schema_version=current.schema_version,
                uploads=[*current.uploads, upload],
            ),
            index_path,
        )
    return True


def update_story_upload(
    upload_id: str,
    uploader_sub: str,
    path: str | Path = DEFAULT_STORY_UPLOAD_PATH,
    **changes,
) -> StoryUpload | None:
    """改自己传的图的名称和默认站位。读改写整个在锁里，顺带复核归属。"""
    index_path = Path(path)
    with _SAVE_LOCK:
        current = load_story_upload_index(index_path)
        existing = current.upload_map.get(upload_id)
        if existing is None or existing.uploader_sub != uploader_sub:
            return None
        updated = StoryUpload.model_validate({**existing.model_dump(), **changes})
        _write(
            StoryUploadIndex(
                schema_version=current.schema_version,
                uploads=[updated if entry.id == upload_id else entry for entry in current.uploads],
            ),
            index_path,
        )
    return updated


def remove_story_upload(upload_id: str, path: str | Path = DEFAULT_STORY_UPLOAD_PATH) -> None:
    index_path = Path(path)
    with _SAVE_LOCK:
        current = load_story_upload_index(index_path)
        _write(
            StoryUploadIndex(
                schema_version=current.schema_version,
                uploads=[entry for entry in current.uploads if entry.id != upload_id],
            ),
            index_path,
        )

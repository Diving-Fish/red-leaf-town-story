from __future__ import annotations

import hashlib
import json
import re
import tempfile
from pathlib import Path

from red_leaf_town.story_assets import StoryAsset, StoryAssetCatalog
from red_leaf_town.story_content import StoryScript, serialize_script


def build_share(raw, subject, assets, partners, uploads):
    if not isinstance(raw, dict):
        raise ValueError("剧本格式不正确")
    script = StoryScript.model_validate({
        **raw,
        "trigger": {"hook": "cue", "params": {"cue": "share"}},
        "rewards": {},
    })
    if script.mode != "stage":
        raise ValueError("分享剧本需要至少一个背景")
    available = {asset.id: asset for asset in assets.assets if not asset.pending}
    for upload in uploads.uploads:
        if upload.uploader_sub == subject:
            available[upload.id] = StoryAsset(
                **upload.model_dump(exclude={"layout"}),
                inline_layout=upload.layout,
                stage_layout=upload.layout,
            )
    for step in script.steps:
        if step.type == "dialogue" or (step.type == "portrait" and not step.visible):
            continue
        if step.asset_id:
            asset = available.get(step.asset_id)
            if asset is None or asset.kind != step.type:
                raise ValueError("剧本引用了不可用的素材，请检查背景和立绘")
        elif step.type == "portrait":
            partner = partners.partner_map.get(step.partner_id)
            if partner is None or partner.artwork_for(step.breakthrough) is None:
                raise ValueError("剧本引用的伙伴插画不存在")
    return serialize_script(script, StoryAssetCatalog(assets=list(available.values())), partners)


def save_share(script: dict, directory: Path) -> str:
    payload = json.dumps(script, ensure_ascii=False, sort_keys=True)
    share_id = hashlib.sha256(payload.encode()).hexdigest()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{share_id}.json"
    if not path.exists():
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=directory, delete=False) as file:
            file.write(payload)
            temporary = Path(file.name)
        temporary.replace(path)
    return share_id


def load_share(share_id: str, directory: Path) -> dict | None:
    if not re.fullmatch(r"[0-9a-f]{64}", share_id):
        return None
    path = directory / f"{share_id}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None

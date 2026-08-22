from __future__ import annotations

from nonebot import on_command
from nonebot.adapters import Bot, Event, Message
from nonebot.params import CommandArg
from nonebot_plugin_alconna import UniMessage

from red_leaf_town.application import GameError
from red_leaf_town.domain import QQIdentity
from red_leaf_town.runtime import get_service
from src.data_access.plugin_manager import plugin_manager


PLUGIN_META = {
    "name": "红叶镇物语",
    "enable": False,
    "help_text": """【红叶镇物语】
  红叶镇                  — 查看农场摘要
  绑定红叶镇 [绑定码]     — 绑定水鱼账号中的红叶镇角色

请先在 Web 端使用水鱼账号登录。""",
}

plugin_manager.register_plugin(PLUGIN_META)


def resolve_identity(bot: Bot, event: Event) -> QQIdentity | None:
    subject = (
        getattr(getattr(event, "author", None), "id", None)
        or getattr(event, "user_id", None)
        or getattr(getattr(event, "data", None), "sender_id", None)
    )
    if not subject:
        return None
    return QQIdentity(platform=str(bot.type), bot_id=str(bot.self_id), subject=str(subject))


def _reply(event: Event, text: str) -> UniMessage:
    message_id = getattr(event, "message_id", None) or getattr(event, "id", None)
    prefix = UniMessage.reply(message_id) if message_id else UniMessage()
    return prefix + UniMessage.text(text)


bind_command = on_command("绑定红叶镇", aliases={"红叶镇绑定"}, force_whitespace=True)


@bind_command.handle()
async def bind_player(bot: Bot, event: Event, message: Message = CommandArg()):
    code = message.extract_plain_text().strip().upper()
    if not code:
        await _reply(event, "请先在红叶镇 Web 页面生成绑定码，再发送『绑定红叶镇 绑定码』。").send()
        return
    identity = resolve_identity(bot, event)
    if not identity:
        await _reply(event, "无法识别当前 QQ 身份，请稍后再试。").send()
        return
    try:
        player = get_service().bind_identity(code, identity)
    except GameError as exc:
        await _reply(event, exc.message).send()
        return
    await _reply(event, f"绑定成功，欢迎回来，{player.display_name}！").send()


summary_command = on_command("红叶镇", force_whitespace=True)


@summary_command.handle()
async def farm_summary(bot: Bot, event: Event):
    identity = resolve_identity(bot, event)
    if not identity:
        await _reply(event, "无法识别当前 QQ 身份。").send()
        return
    try:
        state = get_service().snapshot_by_identity(identity)
    except GameError:
        await _reply(event, "尚未绑定角色。请先登录 Web 端，在账户页生成绑定码。").send()
        return
    player = state["player"]
    ready = sum(1 for plot in state["plots"] if plot["ready"])
    growing = sum(1 for plot in state["plots"] if not plot["empty"] and not plot["ready"])
    working_partners = sum(1 for partner in state["partners"] if partner["locked"])
    await _reply(
        event,
        f"🍁 {player['display_name']} · Lv.{player['level']}\n"
        f"金币：{player['coins']}\n"
        f"体力：{player['stamina']}/{player['stamina_cap']}\n"
        f"伙伴：{state['partner_count']} 位，{working_partners} 位任务中\n"
        f"农田：{ready} 块可收获，{growing} 块生长中\n"
        "前往 Web 页面管理农场：https://chiyuki.diving-fish.com/red-leaf-town/",
    ).send()

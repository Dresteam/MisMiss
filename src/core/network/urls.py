"""Missevan（猫耳FM）API 端点常量。

存放 Missevan 平台所有 HTTP API 与 WebSocket 地址，
以类属性形式组织，便于 IDE 自动补全和统一管理。
"""

from __future__ import annotations

import re


class Urls:
    """Missevan API 端点集合。"""

    # 背包礼物赠送
    BACKPACK_SEND: str = "https://fm.missevan.com/api/v2/chatroom/backpack/send"
    # 机器人信息
    BOT_INFO: str = "https://fm.missevan.com/api/v2/user/mynoble"
    # 机器人状态（背包、等级、携带灯牌）
    BOT_STATUS: str = "https://fm.missevan.com/api/v2/user/status/get"
    # 直售礼物赠送
    GIFT_SEND: str = "https://fm.missevan.com/api/v2/chatroom/gift/send"
    # 消息发送
    MESSAGE_SEND: str = "https://fm.missevan.com/api/chatroom/message/send"
    # 登录房间（刷新背包）
    ONLINE_API: str = "https://fm.missevan.com/api/v2/chatroom/online"
    # 房间信息
    ROOM_INFO: str = "https://fm.missevan.com/api/v2/live/"
    # 聊天室元数据（管理员列表等）
    CHATROOM_META: str = "https://fm.missevan.com/api/v2/chatroom/meta?room_id="
    # 默认 Cookie 获取
    DEFAULT_COOKIE: str = "https://fm.missevan.com/api/user/info"
    # WebSocket 直播弹幕
    LIVE_WEBSOCKET: str = "wss://im.missevan.com/ws?room_id="


# 直播间网页地址（给面板做「打开直播间」跳转用）
LIVE_PAGE_TEMPLATE: str = "https://fm.missevan.com/live/{live_id}"

# 从用户粘贴的内容里抠出直播间 id：允许裸数字，也允许直播间链接。
# 链接形态可能带协议头、www、结尾斜杠、查询串或锚点，故用宽松匹配而不是 URL 解析
_LIVE_ID_RE = re.compile(r"(?:^|/live/)(\d+)(?:\D|$)")


def live_page_url(live_id: int) -> str:
    """直播间网页地址。"""
    return LIVE_PAGE_TEMPLATE.format(live_id=int(live_id))


def parse_live_id(raw: object) -> int:
    """把用户输入解析成直播间 id。

    接受裸数字（``869198039``）、直播间链接
    （``https://fm.missevan.com/live/869198039``、带 / 后缀或 ? 查询串均可），
    也容忍前后空白。解析不出来时抛 :class:`ValueError`。

    :param raw: 用户输入（数字或字符串）
    :return: 直播间 id
    :raises ValueError: 无法解析出合法 id
    """
    if isinstance(raw, bool):  # bool 是 int 的子类，单独挡掉
        raise ValueError("直播间 ID 不合法")
    if isinstance(raw, int):
        if raw > 0:
            return raw
        raise ValueError("直播间 ID 不合法")

    text = str(raw or "").strip()
    if not text:
        raise ValueError("请输入直播间 ID 或直播间链接")

    # 纯数字直接取
    if text.isdigit():
        if int(text) > 0:
            return int(text)
        raise ValueError("直播间 ID 不合法")

    match = _LIVE_ID_RE.search(text)
    if match and int(match.group(1)) > 0:
        return int(match.group(1))
    raise ValueError(f"无法从「{text}」中解析出直播间 ID，请粘贴直播间链接或直接填数字")

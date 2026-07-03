"""Missevan（猫耳FM）API 端点常量。

存放 Missevan 平台所有 HTTP API 与 WebSocket 地址，
以类属性形式组织，便于 IDE 自动补全和统一管理。
"""


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

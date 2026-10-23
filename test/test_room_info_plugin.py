"""直播间信息插件测试（无网络）。

覆盖：数据解析、分区名称、时长格式、输出格式、消息拆分、权限与冷却。

运行: .venv/Scripts/python.exe test/test_room_info_plugin.py
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from interfaces.plugin.miss_config import MissConfig  # noqa: E402

_PATH = os.path.join(os.path.dirname(__file__), "..", "plugins", "room_info", "main.py")
_spec = importlib.util.spec_from_file_location("room_info_test", _PATH)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]
RoomInfoPlugin = _mod.RoomInfoPlugin

_passed = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global _passed
    if not cond:
        raise AssertionError(f"FAIL: {label} {detail}")
    _passed += 1
    print(f"PASS {_passed}: {label}")


NOW = 1_700_000_000.0

ROOM_INFO = {
    "code": 0,
    "info": {
        "room": {
            "catalog_id": 140,
            "custom_tag_id": 20014,
            "status": {"open": 1, "open_time": int((NOW - 2 * 3600 - 169) * 1000)},
            "statistics": {
                "accumulation": 1644,
                "attention_count": 18401,
                "score": 456,
            },
            "medal": {"name": "z野玫瑰"},
        }
    },
}

CHATROOM_META = {
    "code": 0,
    "info": {"hour_rank": {"rank": 51, "rank_up": 22992}},
}

VIP_INFO = {"code": 0, "info": {"vip_num": 7, "Datas": []}}
SUPERFAN_INFO = {
    "code": 0,
    "info": {"data": [], "pagination": {"count": 4, "maxpage": 0, "p": 1}},
}
CATALOG_INFO = {
    "code": 0,
    "info": {
        "catalogs": [
            {
                "catalog_id": 116,
                "catalog_name": "情感",
                "sub_catalogs": [{"catalog_id": 140, "catalog_name": "闲聊"}],
            }
        ],
        "custom_tag_groups": [],
    },
}


def make_snapshot(plugin) -> dict:
    return plugin._parse_snapshot(
        ROOM_INFO, CHATROOM_META, VIP_INFO, SUPERFAN_INFO, CATALOG_INFO, now=NOW
    )


class FakeLive:
    def __init__(self) -> None:
        self.live_id = 123
        self.sent: list[str] = []

    async def send_message(self, message: str) -> None:
        self.sent.append(message)


def make_event(message: str, name: str, is_admin: bool, live: FakeLive) -> SimpleNamespace:
    return SimpleNamespace(
        message=message,
        user=SimpleNamespace(name=name, id=10001, is_admin=is_admin),
        livestream=live,
    )


async def main() -> None:
    # ---- 1. 元数据 / 配置 schema ----
    import yaml

    meta_path = os.path.join(os.path.dirname(_PATH), "metadata.yaml")
    with open(meta_path, encoding="utf-8") as f:
        meta = yaml.safe_load(f)
    check("metadata 名称正确", meta["name"] == "room_info", str(meta))
    schema_path = os.path.join(os.path.dirname(_PATH), "_conf_schema.json")
    with open(schema_path, encoding="utf-8") as f:
        schema = json.load(f)
    check("配置 schema 默认仅房管", schema["admin_only"]["default"] is True)
    check("配置 schema 默认指令", schema["cmd"]["default"] == "直播间")

    plugin = RoomInfoPlugin({})
    plugin._config = MissConfig({})

    # ---- 2. 时长与分区 ----
    check(
        "时长格式 02:02:49",
        plugin._format_duration(ROOM_INFO["info"]["room"]["status"]["open_time"], True, NOW)
        == "02:02:49",
    )
    check("未开播显示未开播", plugin._format_duration(None, False) == "未开播")
    check(
        "分区映射 情感-闲聊",
        plugin._catalog_label(CATALOG_INFO, 140) == "情感-闲聊",
    )
    check("未知分区返回 None", plugin._catalog_label(CATALOG_INFO, 999) is None)

    # ---- 3. 解析 ----
    snap = make_snapshot(plugin)
    check("房间可用", snap["room_ok"] is True)
    check("累计人数", snap["accumulation"] == 1644, str(snap))
    check("关注数", snap["attention"] == 18401, str(snap))
    check("热度", snap["score"] == 456, str(snap))
    check("超粉", snap["superfan"] == 4, str(snap))
    check("贵宾", snap["vip"] == 7, str(snap))
    check("小时榜", snap["hour_rank"] == 51, str(snap))
    check("小时榜差值", snap["hour_gap"] == 22992, str(snap))
    check("勋章", snap["medal"] == "z野玫瑰", str(snap))

    # ---- 4. 输出 ----
    text = plugin._format(snap, "触发人", MissConfig({}))
    for label in (
        "直播间数据：",
        "🎤分区：情感-闲聊",
        "⏰直播时长：02:02:49",
        "👪累计人数：1644",
        "💗关注数：18401",
        "☀️热度：456",
        "👩超粉：4",
        "🍁贵宾：7",
        "🏅️小时榜：51",
        "💰小时榜差值/距离上榜：22992",
        "📛勋章：z野玫瑰",
    ):
        check(f"输出包含 {label}", label in text, text)
    for unsupported in (
        "分区排名",
        "热度排名",
        "Banner位",
        "推荐位",
        "福星榜",
        "PK胜率",
    ):
        check(f"不输出未实现项 {unsupported}", unsupported not in text, text)
    check("默认 @ 触发人", text.startswith("@触发人"), text.splitlines()[0])

    compact = plugin._format(
        {**snap, "catalog": None}, "触发人", MissConfig({"show_unknown": False})
    )
    check("可隐藏缺失字段", "🎤分区" not in compact, compact)
    check("仍保留有值行", "🍁贵宾：7" in compact, compact)

    no_mention = plugin._format(snap, "触发人", MissConfig({"mention": False}))
    check("可关闭 @", not no_mention.startswith("@"))

    failed = plugin._format(
        {"room_ok": False}, "触发人", MissConfig({})
    )
    check("房间信息失败给出提示", "暂时获取不到" in failed, failed)

    # ---- 5. 消息拆分 ----
    chunks = plugin._split_message("a\nbb\nccc\ndddd", 5)
    check("按行拆分且不超限", all(len(c) <= 5 for c in chunks), str(chunks))
    check("拆分后可还原", "\n".join(chunks) == "a\nbb\nccc\ndddd", str(chunks))
    check("短消息不拆", plugin._split_message("abc", 10) == ["abc"])

    # ---- 6. 权限与冷却 ----
    snap_data = snap

    async def fake_snapshot(room_id, cfg):
        return snap_data

    plugin._snapshot = fake_snapshot  # type: ignore[method-assign]

    live = FakeLive()
    await plugin.on_message(make_event("直播间", "房管", True, live))
    check("房管可用", len(live.sent) == 1 and "直播间数据" in live.sent[0])

    live = FakeLive()
    await plugin.on_message(make_event("直播间", "路人", False, live))
    check("非房管默认静默", live.sent == [])

    plugin._config = MissConfig({"cooldown_seconds": 0, "deny_reply": "仅房管可用"})
    live = FakeLive()
    await plugin.on_message(make_event("直播间", "路人", False, live))
    check("无权限可回复提示", live.sent == ["仅房管可用"], str(live.sent))

    plugin._config = MissConfig(
        {
            "cooldown_seconds": 0,
            "allowed_users": ["路人"],
            "cmd_aliases": ["直播数据"],
        }
    )
    live = FakeLive()
    await plugin.on_message(make_event("直播数据", "路人", False, live))
    check("白名单可用且支持别名", len(live.sent) == 1, str(live.sent))

    plugin._config = MissConfig({"cooldown_seconds": 0, "admin_only": False})
    live = FakeLive()
    await plugin.on_message(make_event("直播间", "路人", False, live))
    check("关闭 admin_only 后所有人可用", len(live.sent) == 1)

    # 冷却：新实例，避免上面积累的 _last_reply
    cooled = RoomInfoPlugin({})
    cooled._config = MissConfig({"cooldown_seconds": 60})
    cooled._snapshot = fake_snapshot  # type: ignore[method-assign]
    live = FakeLive()
    await cooled.on_message(make_event("直播间", "房管", True, live))
    await cooled.on_message(make_event("直播间", "房管", True, live))
    check("冷却期内只回一次", len(live.sent) == 1, str(live.sent))

    # 其他消息不触发
    live = FakeLive()
    await plugin.on_message(make_event("你好", "房管", True, live))
    check("非指令不触发", live.sent == [])

    print("\n全部通过")


if __name__ == "__main__":
    asyncio.run(main())

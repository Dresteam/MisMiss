"""重复实例 / 歌单插件回归测试（无网络）。

覆盖：
- 并发 enable 同一插件只创建一个实例、只注册一次事件监听
- Bot.close() 取消定时器与消费者，且之后不会再被恢复流程拉起来
- 并发 join 同一直播间只建立一条 WebSocket
- 歌单插件在「先启用插件、后绑定直播间」时仍能解析房间并发送
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
import tempfile
from pathlib import Path

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "src"))
sys.path.insert(0, os.path.join(_ROOT, "web", "backend"))

os.environ["MISMISS_DATA_DIR"] = tempfile.mkdtemp(prefix="mismiss-dup-guard-")

from core.bot.mis_bot import MissevanBot  # noqa: E402
from core.events.bus import EventBus  # noqa: E402
from core.livestream.mis_livestream import MissevanLivestream  # noqa: E402
from core.plugin.plugin_manager import PluginManager  # noqa: E402
from core.server import MissevanServer  # noqa: E402
from interfaces.plugin.miss_config import MissConfig  # noqa: E402

_passed = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global _passed
    if not cond:
        raise AssertionError(f"FAIL: {label} {detail}")
    _passed += 1
    print(f"PASS {_passed}: {label}")


def _write_demo_plugin(root: Path) -> None:
    plugin = root / "demo"
    plugin.mkdir(parents=True)
    (plugin / "metadata.yaml").write_text(
        "name: demo\n"
        "desc: demo\n"
        "author: test\n"
        "version: 1.0.0\n"
        "short_desc: demo\n"
        "display_name: Demo\n",
        encoding="utf-8",
    )
    (plugin / "main.py").write_text(
        "import asyncio\n"
        "from interfaces.plugin import Plugin\n"
        "\n"
        "class Demo(Plugin):\n"
        "    init_calls = 0\n"
        "\n"
        "    async def initialize(self, config):\n"
        "        type(self).init_calls += 1\n"
        "        await asyncio.sleep(0.1)\n",
        encoding="utf-8",
    )


async def test_concurrent_enable_single_instance() -> None:
    base = Path(tempfile.mkdtemp(prefix="mismiss-plugin-lock-"))
    _write_demo_plugin(base / "plugins")
    bus = EventBus()
    pm = PluginManager(
        str(base / "plugins"), bus, str(base / "config"),
        permission_dir=str(base / "permissions"),
        plugin_data_dir=str(base / "plugin_data"),
    )
    await pm.load_all()
    await asyncio.gather(pm.enable_plugin("demo"), pm.enable_plugin("demo"))
    meta = pm.get_plugin("demo")
    check("并发启用后存在实例", meta is not None and meta.plugin_instance is not None)
    instance = meta.plugin_instance  # type: ignore[union-attr]
    check(
        "事件总线只注册一次",
        sum(1 for item in bus._listeners if item is instance) == 1,
        str(len(bus._listeners)),
    )
    check(
        "initialize 只执行一次",
        meta.module.Demo.init_calls == 1,  # type: ignore[union-attr]
        str(meta.module.Demo.init_calls),  # type: ignore[union-attr]
    )
    await pm.shutdown_all()
    check("shutdown 后实例已注销", not any(item is instance for item in bus._listeners))


async def test_bot_close_stops_background() -> None:
    bot = MissevanBot("")
    bot.timer_interval = 1
    bot.register_timer_message(0, "定时消息")
    check("定时器已启动", bot._timer_task is not None)
    await bot.close()
    check("close 后定时器为空", bot._timer_task is None)
    check("close 后消费者为空", bot._consumer_task is None)
    check("close 后标记关闭", bot._closed is True and bot.enabled is False)

    bot.restore_timer_state(
        {"global": [{"message_id": "m1", "message": "恢复的定时消息"}]}
    )
    check("关闭后 restore 不会再拉起定时器", bot._timer_task is None)


class _FakeWS:
    def __init__(self) -> None:
        self.connect_count = 0

    async def connect(self) -> None:
        self.connect_count += 1
        await asyncio.sleep(0.05)

    async def close(self) -> None:
        pass


async def test_join_is_serialized() -> None:
    bus = EventBus()
    live = MissevanLivestream(123, MissevanBot(""), bus)
    live.enabled = True

    async def fake_refresh(*args, **kwargs) -> None:
        return None

    live._refresh = fake_refresh  # type: ignore[method-assign]
    ws = _FakeWS()
    live._create_websocket = lambda: ws  # type: ignore[method-assign]
    await asyncio.gather(live.join(), live.join())
    check("并发 join 只连接一次", ws.connect_count == 1, str(ws.connect_count))


class _FakeLive:
    def __init__(self, live_id: int) -> None:
        self.live_id = live_id
        self.sent: list[str] = []

    async def send_message(self, message: str) -> None:
        self.sent.append(message)


class _FakeServer:
    def __init__(self, rooms: dict[int, _FakeLive]) -> None:
        self.livestreams = rooms


class _FakeMessageEvent:
    def __init__(self, message: str) -> None:
        self.message = message


async def test_song_list_resolves_room() -> None:
    base = Path(tempfile.mkdtemp(prefix="mismiss-songlist-"))
    shutil.copytree(Path(_ROOT) / "plugins" / "song_list", base / "plugins" / "song_list")
    bus = EventBus()
    pm = PluginManager(
        str(base / "plugins"), bus, str(base / "config"),
        permission_dir=str(base / "permissions"),
        plugin_data_dir=str(base / "plugin_data"),
    )
    rooms: dict[int, _FakeLive] = {}
    pm.set_server(_FakeServer(rooms))
    await pm.load_all()
    await pm.enable_plugin("song_list")
    meta = pm.get_plugin("song_list")
    plugin = meta.plugin_instance  # type: ignore[union-attr]

    # 先启用、后绑定（真实账户常见顺序）
    live = _FakeLive(123)
    rooms[123] = live
    await plugin.on_livestream_bound(live)
    await plugin.on_message(_FakeMessageEvent("歌单"))
    check("歌单已发送", len(live.sent) == 1, str(live.sent))
    check("歌单内容含标题", "本场歌单" in live.sent[0], live.sent[0][:80])

    # 缓存房间号失效时也能重新解析
    plugin._room_id = 999
    await plugin.on_message(_FakeMessageEvent("歌单"))
    check("失效缓存可重新解析", len(live.sent) == 2, str(len(live.sent)))

    # 分页 + 自定义指令
    plugin._config = MissConfig({
        "cmd": "本场歌单",
        "cmd_aliases": ["歌单"],
        "page_size": 2,
        "max_chars": 500,
        "song_list": ["歌1", "歌2", "歌3", "歌4", "歌5"],
        "header": "HEADER",
        "footer": "FOOTER",
        "page_line": "({page}/{total}) 发「{cmd} {next}」",
    })
    live.sent.clear()
    await plugin.on_message(_FakeMessageEvent("本场歌单 2"))
    check("自定义指令可翻页", len(live.sent) == 1, str(live.sent))
    check("第 2 页页码正确", "(2/3)" in live.sent[0], live.sent[0])
    check(
        "第 2 页只含第 3、4 首",
        "歌3" in live.sent[0] and "歌2" not in live.sent[0],
        live.sent[0],
    )

    live.sent.clear()
    await plugin.on_message(_FakeMessageEvent("歌单 3"))
    check("别名也可翻页", "(3/3)" in live.sent[0], live.sent[0])
    check("第 3 页含第 5 首", "歌5" in live.sent[0], live.sent[0])

    # 超长时拆成多条，且每块不超过 max_chars
    plugin._config = MissConfig({
        "cmd": "歌单",
        "page_size": 5,
        "max_chars": 40,
        "song_list": ["很长很长很长很长很长很长的歌名1", "很长很长很长很长很长很长的歌名2", "歌3"],
        "header": "HEADER",
        "footer": "FOOTER",
    })
    live.sent.clear()
    await plugin.on_message(_FakeMessageEvent("歌单"))
    check("超长歌单拆成多条", len(live.sent) > 1, str([len(x) for x in live.sent]))
    check("每条不超过上限", all(len(x) <= 40 for x in live.sent), str([len(x) for x in live.sent]))

    # 分页预算：6 首长行不应把第 6 首挤到第二条消息里
    plugin._config = MissConfig({
        "cmd": "歌单",
        "page_size": 6,
        "max_chars": 180,
        "song_list": [f"很长的歌名{i}号" * 5 for i in range(1, 7)],
        "header": "★--☁ 本场歌单 ☁--★",
        "footer": "══════",
    })
    live.sent.clear()
    await plugin.on_message(_FakeMessageEvent("歌单"))
    check("按字符预算分页后只发一条", len(live.sent) == 1, str([len(x) for x in live.sent]))
    check("页面显示 1/2 页", "(1/2页)" in live.sent[0], live.sent[0])
    check("第 4 首不会挤进第 1 页", "❥•4" not in live.sent[0], live.sent[0])

    # 不是指令的消息不回复
    live.sent.clear()
    await plugin.on_message(_FakeMessageEvent("歌单列表"))
    check("非指令消息不误触发", not live.sent, str(live.sent))

    await pm.shutdown_all()


async def test_bot_disable_stops_timer() -> None:
    """停用 Bot 应立即停掉定时循环与消费者，而不是每 tick 打「跳过」日志。"""
    bot = MissevanBot("")
    bot.register_timer_message(0, "停用前注册的定时消息")
    check("停用前定时器在跑", bot._timer_task is not None)
    bot.enabled = False
    await asyncio.sleep(0.05)
    check("停用后定时器已取消", bot._timer_task is None)
    check("定时消息仍保留（便于启用时恢复）", bot.timer_message_count > 0)
    bot.enabled = True
    bot._ensure_timer_running()
    check("重新启用后定时器恢复", bot._timer_task is not None)
    await bot.close()


async def test_create_bot_stops_old_timer() -> None:
    """切 Cookie/切模式后旧 Bot 的定时器必须停掉，不能继续用旧 Cookie 播报。"""
    base = Path(tempfile.mkdtemp(prefix="mismiss-bot-replace-"))
    server = MissevanServer(data_dir=str(base), state_file="server_state.json")
    old = server._bot
    old.register_timer_message(0, "旧 Cookie 的定时消息")
    check("旧 Bot 定时器已启动", old._timer_task is not None)

    original_refresh = MissevanBot.refresh

    async def fake_refresh(self: MissevanBot):
        self._id = 1
        self._name = "fake"
        return self

    MissevanBot.refresh = fake_refresh  # type: ignore[method-assign]
    try:
        await server.create_bot("new-cookie")
    finally:
        MissevanBot.refresh = original_refresh  # type: ignore[method-assign]

    check("旧 Bot 已标记关闭", old._closed is True)
    check("旧 Bot 定时器已取消", old._timer_task is None)
    check("新 Bot 已接管", server._bot is not old and server._bot.id == 1)
    check(
        "定时消息已迁移到新 Bot",
        server._bot.timer_message_count > 0,
        str(server._bot.timer_message_count),
    )
    await server.shutdown()


async def main() -> None:
    await test_concurrent_enable_single_instance()
    await test_bot_close_stops_background()
    await test_bot_disable_stops_timer()
    await test_create_bot_stops_old_timer()
    await test_join_is_serialized()
    await test_song_list_resolves_room()
    print("\n全部通过")


if __name__ == "__main__":
    asyncio.run(main())

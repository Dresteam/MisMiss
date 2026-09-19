"""插件日志来源过滤 + 初始化失败记录 测试(无网络)。

覆盖:`_is_plugin_source()` 对四类路径的判定、环形缓冲的 plugin_only 过滤、
API 产物不含服务器路径、插件初始化失败时写入 last_error 且用 _log.exception
输出含 traceback 的日志、插件不再进任何「失败列表」。

运行: .venv/Scripts/python.exe test/test_plugin_log_scope.py
"""
import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "web", "backend"))

from api.routes.ws import RingBuffer, _is_plugin_source  # noqa: E402

REPO = r"E:\repo"


def test_source_predicate():
    cases = [
        (rf"{REPO}\plugins\nickname\main.py", True, "插件库源码"),
        (rf"{REPO}\data\accounts\3\installed_plugins\nickname\main.py", True, "账户副本"),
        (rf"{REPO}\src\core\plugin\plugin_manager.py", True, "框架插件生命周期"),
        (rf"{REPO}\src\core\bot\mis_bot.py", False, "Bot 业务代码"),
        (rf"{REPO}\src\core\server.py", False, "服务器业务代码"),
        (rf"{REPO}\src\core\logging.py", False, "日志基础设施"),
        ("", False, "空路径(模块级 log 无 path)"),
        ("/opt/app/plugins/x/main.py", True, "POSIX 路径"),
    ]
    for path, want, label in cases:
        got = _is_plugin_source(path)
        assert got is want, f"FAIL: {label} 期望 {want} 实际 {got} ({path})"
    print(f"PASS 1: _is_plugin_source 判定正确 ({len(cases)} 类路径)")


def test_ring_buffer_scope():
    buf = RingBuffer(capacity=100)
    buf.append("INFO", "业务日志", source="MisBot", path=rf"{REPO}\src\core\bot\mis_bot.py")
    buf.append("ERROR", "插件炸了", source="NicknamePlugin",
               path=rf"{REPO}\plugins\nickname\main.py")
    buf.append("INFO", "框架插件日志", source="PluginManager",
               path=rf"{REPO}\src\core\plugin\plugin_manager.py")
    buf.append("WARNING", "服务器日志", source="MissevanServer",
               path=rf"{REPO}\src\core\server.py")

    all_entries, _, total_all = buf.get_since(0, 50)
    plugin_entries, _, total_plugin = buf.get_since(0, 50, plugin_only=True)

    assert total_all == 4, f"FAIL: 全部条目应为 4, 实际 {total_all}"
    assert total_plugin == 2, f"FAIL: 插件相关应为 2, 实际 {total_plugin}"
    assert [e["source"] for e in plugin_entries] == ["NicknamePlugin", "PluginManager"], \
        f"FAIL: 来源错误 {[e['source'] for e in plugin_entries]}"
    print("PASS 2: plugin_only 只返回插件相关日志")

    # API 产物含 source 供展示，但不含服务器绝对路径
    assert "source" in all_entries[0], "FAIL: 产物缺少 source"
    assert "path" not in all_entries[0], "FAIL: 产物泄漏了服务器路径 path"
    assert set(all_entries[0]) == {
        "seq_id", "timestamp", "level", "message", "source", "account",
    }, f"FAIL: 产物字段意外 {sorted(all_entries[0])}"
    print("PASS 3: API 产物含 source 且不含 path")

    # 级别 + 来源两个维度可叠加
    both, _, total_both = buf.get_since(0, 50, levels={"ERROR"}, plugin_only=True)
    assert total_both == 1 and both[0]["source"] == "NicknamePlugin", f"FAIL: {both}"
    print("PASS 4: levels 与 plugin_only 可叠加过滤")


def _install_failing_plugin(plugin_dir: str):
    """造一个 initialize 必定抛异常的插件。"""
    d = os.path.join(plugin_dir, "boom_plugin")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "metadata.yaml"), "w", encoding="utf-8") as f:
        f.write(
            "name: boom_plugin\n"
            "author: Test\n"
            "desc: 初始化必抛异常\n"
            "version: 1.0.0\n"
        )
    with open(os.path.join(d, "main.py"), "w", encoding="utf-8") as f:
        f.write(
            "from interfaces.plugin import Plugin\n"
            "from interfaces.plugin.miss_config import MissConfig\n"
            "\n"
            "class BoomPlugin(Plugin):\n"
            "    async def initialize(self, config: MissConfig) -> None:\n"
            "        raise RuntimeError('故意爆炸')\n"
        )
    return d


async def test_init_failure():
    """插件初始化抛异常：写入 last_error、寄存器里出现含 traceback 的日志。"""
    from core.events.bus import EventBus
    from core.exceptions import CorePluginLoadException
    from core.plugin.plugin_manager import PluginManager

    tmp = tempfile.mkdtemp(prefix="mismiss-logscope-")
    plugin_dir = os.path.join(tmp, "plugins")
    os.makedirs(plugin_dir, exist_ok=True)
    _install_failing_plugin(plugin_dir)

    pm = PluginManager(
        plugin_dir=plugin_dir,
        event_bus=EventBus(),
        config_dir=os.path.join(tmp, "config"),
        permission_dir=os.path.join(tmp, "permissions"),
        plugin_data_dir=os.path.join(tmp, "pdata"),
    )
    await pm.load_all()
    meta = pm.get_plugin("boom_plugin")
    assert meta is not None, "FAIL: 插件未被发现"
    assert meta.last_error is None, "FAIL: 未启用前不应有 last_error"

    # 捕获日志：用一个临时 sink 收集本插件初始化期间的记录
    from loguru import logger as _lg
    captured: list = []
    sink_id = _lg.add(lambda m: captured.append(m.record), level="ERROR")

    raised = False
    try:
        await pm.enable_plugin("boom_plugin")
    except CorePluginLoadException:
        raised = True
    finally:
        _lg.remove(sink_id)

    assert raised, "FAIL: 初始化失败应抛 CorePluginLoadException"
    assert meta.last_error and "故意爆炸" in meta.last_error, \
        f"FAIL: last_error 未写入或内容不对 {meta.last_error!r}"
    assert meta.enabled is False, "FAIL: 失败后应为禁用状态"
    print(f"PASS 5: 初始化失败写入 last_error ({meta.last_error!r})")

    # _log.exception 应输出带 traceback 的记录
    msgs = [str(r["message"]) for r in captured]
    hit = [m for m in msgs if "boom_plugin" in m and "初始化失败" in m]
    assert hit, f"FAIL: 日志里没有初始化失败记录 {msgs[-3:]}"
    formatted = str(captured[[i for i, r in enumerate(captured)
                              if "boom_plugin" in str(r["message"])][-1]]["exception"])
    assert "RuntimeError" in formatted and "故意爆炸" in formatted, \
        f"FAIL: 日志未包含 traceback\n{formatted[:300]}"
    print("PASS 6: 初始化失败用 _log.exception 输出了含 traceback 的日志")

    # 失败插件不再进任何「失败列表」，且没有遗留的失败字典
    assert not hasattr(pm, "_failed_plugins"), "FAIL: _failed_plugins 应已移除"
    for gone in ("get_failed_plugins", "retry_failed_plugin", "discard_failed_plugin"):
        assert not hasattr(pm, gone), f"FAIL: {gone} 应已移除"
    print("PASS 7: 失败插件列表机制已彻底移除")


async def main() -> None:
    test_source_predicate()
    test_ring_buffer_scope()
    await test_init_failure()
    print("\n全部通过")


if __name__ == "__main__":
    asyncio.run(main())

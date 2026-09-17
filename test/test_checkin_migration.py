"""签到插件账户级迁移测试(无网络)。

原实现按直播间分区存储(room_id → user_id → date),账户更换绑定直播间后
旧数据再也读不到。现已改为账户级单份,并在载入时扁平化合并旧的房间分区数据。
本测试锁住:新格式往返、旧格式兼容合并、跨房间取较大次数、签到流程正常。

运行: .venv/Scripts/python.exe test/test_checkin_migration.py
"""
import asyncio
import importlib.util
import os
import sys
from datetime import date, timedelta
from types import SimpleNamespace

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "src"))

sys.stdout.reconfigure(errors="replace")

from interfaces.plugin.miss_config import MissConfig  # noqa: E402

res: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    res.append((name, cond, detail))


class _Store:
    """替身 PluginDataManager：内存中保留最后一次写入的 JSON。"""

    def __init__(self, initial=None) -> None:
        self.saved: dict | None = initial

    def read_json(self, _name: str):
        return self.saved

    def write_json(self, _name: str, data) -> None:
        self.saved = data


def _load_plugin():
    path = os.path.join(_ROOT, "plugins", "checkin", "main.py")
    spec = importlib.util.spec_from_file_location(
        "checkin_mig_test", path, submodule_search_locations=[os.path.dirname(path)]
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["checkin_mig_test"] = module
    spec.loader.exec_module(module)
    return module


def _plugin(module, store):
    p = module.CheckinPlugin()
    p.name = "checkin"
    p._config = MissConfig({
        "cmd_checkin": "签到",
        "cmd_checkin_aliases": ["打卡", "dd"],
        "stat_total": "┊ 🎐 累计：{v}",
        "stat_month": "┊ 🎐 本月：{v}",
        "stat_week": "┊ 🎐 本周：{v}",
        "stat_streak": "┊ 🎐 连续：{v}",
    })
    p.data = store
    return p


async def main() -> None:
    module = _load_plugin()
    today = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()

    # ---- 1. 新格式往返 ----
    store = _Store({"checkins": {"u1": {today: 1}}})
    p = _plugin(module, store)
    p._load_data()
    check("新格式载入", p._checkins == {"u1": {today: 1}}, f"{p._checkins}")
    p._save_data()
    check("新格式保存结构", set(store.saved.keys()) == {"checkins"}
          and "u1" in store.saved["checkins"], f"{store.saved}")

    # ---- 2. 旧格式（房间分区）扁平化合并 ----
    store = _Store({"checkins": {
        "12345": {"u1": {yesterday: 1}, "u2": {today: 1}},
        "67890": {"u1": {today: 1}},
    }, "rooms": {"12345": "老房间"}})
    p = _plugin(module, store)
    p._load_data()
    check("旧房间分区被扁平化",
          set(p._checkins.keys()) == {"u1", "u2"}, f"{p._checkins}")
    check("跨房间同一用户合并（日期并集）",
          p._checkins["u1"] == {yesterday: 1, today: 1}, f"{p._checkins['u1']}")

    # ---- 3. 跨房间同一日期取较大次数 ----
    store = _Store({"checkins": {
        "12345": {"u1": {today: 1}},
        "67890": {"u1": {today: 3}},
    }})
    p = _plugin(module, store)
    p._load_data()
    check("同一日期取较大次数", p._checkins["u1"][today] == 3, f"{p._checkins['u1']}")

    # ---- 4. 签到流程：首次打卡 + 今日排名 ----
    store = _Store(None)
    p = _plugin(module, store)
    p._load_data()
    sent: list[str] = []

    class _Live:
        def __init__(self) -> None:
            self.bot = None
            self.room_name = "测试直播间"

        async def send_message(self, m: str, priority: int = 0) -> None:
            sent.append(m)

    def _event(uid: int, name: str):
        return SimpleNamespace(
            message="签到",
            user=SimpleNamespace(id=uid, name=name, is_admin=False),
            livestream=_Live(),
        )

    await p.on_message(_event(1, "甲"))
    check("首次打卡已记录", p._checkins.get("1", {}).get(today) == 1, f"{p._checkins}")
    check("首次打卡消息含排名", any("第1位" in m for m in sent), f"{sent}")
    check("首次打卡后已落盘", store.saved is not None and "1" in store.saved["checkins"],
          f"{store.saved}")

    sent.clear()
    await p.on_message(_event(2, "乙"))
    check("第二位打卡排名为 2", any("第2位" in m for m in sent), f"{sent}")

    sent.clear()
    await p.on_message(_event(1, "甲"))
    check("重复打卡走统计消息", any("已经打过卡" in m for m in sent), f"{sent}")

    # ---- 5. 连续签到统计基于账户级记录 ----
    recs = {today: 1, yesterday: 1}
    stats = module.CheckinPlugin._calc_stats(recs, date.today())
    check("连续签到计数正确", stats["streak"] == 2, f"{stats}")

    for name, ok, detail in res:
        print(("PASS " if ok else "FAIL ") + name + ("" if ok else f"   [{detail}]"))
    print("---")
    print("全部通过" if all(r[1] for r in res) else "存在失败项")


if __name__ == "__main__":
    asyncio.run(main())

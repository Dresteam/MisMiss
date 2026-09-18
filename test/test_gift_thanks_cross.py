"""礼物感谢插件「跨房礼物感谢」功能测试(无网络)。

覆盖:开关生效、受赠主播标注行、关闭时不发送、本房礼物不受影响、
同名不同受赠主播不合并、批量聚合路径同样带标注。

运行: .venv/Scripts/python.exe test/test_gift_thanks_cross.py
"""
import asyncio
import importlib.util
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "src"))

# 控制台默认 GBK：消息里的制表符（┆）等字符打不出来会直接抛异常，降级为替换符
sys.stdout.reconfigure(errors="replace")

from interfaces.plugin.miss_config import MissConfig  # noqa: E402
from interfaces.entity.gift import Gift  # noqa: E402
from core.models.events import CrossGiftEvent, GiftEvent  # noqa: E402

res: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    res.append((name, cond, detail))


class _Live:
    """假直播间：记录发出的消息。"""

    def __init__(self) -> None:
        self.bot = None
        self.sent: list[str] = []

    async def send_message(self, message: str, priority: int = 0) -> None:
        self.sent.append(message)


class _User:
    def __init__(self, uid: int = 38214227, name: str = "_莓柿") -> None:
        self.id = uid
        self.name = name
        self.is_admin = False


def _gift(name: str = "喵卡龙", num: int = 1, price: int = 1) -> Gift:
    from core.models.gift import LiveGift

    return LiveGift(
        gift_livestream=None, gift_user=None, gift_id=1,
        gift_name=name, gift_price=price, gift_num=num, gift_lucky=None,
    )


def _load_plugin():
    """按文件路径加载插件模块（与框架一致的加载方式）。"""
    path = os.path.join(_ROOT, "plugins", "gift_thanks", "main.py")
    spec = importlib.util.spec_from_file_location(
        "gt_cross_test", path, submodule_search_locations=[os.path.dirname(path)]
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["gt_cross_test"] = module
    spec.loader.exec_module(module)
    return module


def _cfg(**over) -> MissConfig:
    base = {
        "batch_enabled": False,
        "cross_gift_enabled": True,
        "cross_gift_line": "┆　• 送给：{target}",
        "thank_prefix": "感谢投喂：",
        "header_art": "",
        "footer_art": "",
    }
    base.update(over)
    return MissConfig(base)


def _plugin(module, cfg):
    plugin = module.GiftThanksPlugin()
    plugin.name = "gift_thanks"
    plugin._config = cfg
    return plugin


async def main() -> None:
    module = _load_plugin()

    # ---- 1. 开关关闭：跨房礼物不发送 ----
    live = _Live()
    plugin = _plugin(module, _cfg(cross_gift_enabled=False))
    await plugin.on_cross_gift(CrossGiftEvent(
        event_livestream=live, event_user=_User(), event_gift=_gift(),
        event_target_creator_name="s_晴天",
    ))
    check("开关关闭时不发送跨房感谢", live.sent == [], f"{live.sent}")

    # ---- 2. 开关开启：发送且带受赠主播标注 ----
    live = _Live()
    plugin = _plugin(module, _cfg())
    await plugin.on_cross_gift(CrossGiftEvent(
        event_livestream=live, event_user=_User(), event_gift=_gift(),
        event_target_creator_name="s_晴天",
    ))
    msg = live.sent[0] if live.sent else ""
    check("开关开启时发送跨房感谢", len(live.sent) == 1, f"{live.sent}")
    check("消息含受赠主播标注行", "┆　• 送给：s_晴天" in msg, f"{msg!r}")
    check("消息含礼物名", "喵卡龙" in msg, f"{msg!r}")

    # ---- 3. 受赠主播未知（平台未带 room）→ 不输出标注行 ----
    live = _Live()
    plugin = _plugin(module, _cfg())
    await plugin.on_cross_gift(CrossGiftEvent(
        event_livestream=live, event_user=_User(), event_gift=_gift(),
    ))
    check("受赠主播未知时不输出标注行",
          len(live.sent) == 1 and "送给：" not in live.sent[0], f"{live.sent}")

    # ---- 4. 本房礼物不受影响（不带标注行） ----
    live = _Live()
    plugin = _plugin(module, _cfg())
    await plugin.on_gift(GiftEvent(
        event_livestream=live, event_user=_User(), event_gift=_gift(),
    ))
    check("本房礼物不带跨房标注行",
          len(live.sent) == 1 and "送给：" not in live.sent[0], f"{live.sent}")

    # ---- 5-8. 合并与聚合（走批量路径：同一批只发一条消息） ----
    import collections

    async def batch_message(targets: list[str]) -> tuple[str, int]:
        """连续投递若干跨房礼物，返回（聚合后的消息, 发出的消息条数）。"""
        batch_live = _Live()
        batch_plugin = _plugin(module, _cfg(batch_enabled=True, batch_delay=0.05))
        batch_plugin._batches = collections.defaultdict(module._UserBatch)
        for target in targets:
            await batch_plugin.on_cross_gift(CrossGiftEvent(
                event_livestream=batch_live, event_user=_User(), event_gift=_gift(),
                event_target_creator_name=target,
            ))
        await asyncio.sleep(0.25)  # 等待聚合计时器触发
        return (batch_live.sent[0] if batch_live.sent else ""), len(batch_live.sent)

    msg, n = await batch_message(["s_晴天"])
    check("聚合路径同样输出受赠主播标注",
          n == 1 and "送给：s_晴天" in msg, f"n={n} {msg!r}")

    # v1.3.4 起：同名礼物合并成一行，受赠主播以顿号接在同一行尾——
    # 此前是每个受赠主播各占一行，多行看起来完全重复且与礼物无视觉对应
    msg, n = await batch_message(["s_晴天", "小美"])
    check("同名不同受赠主播合并成一行",
          n == 1 and "s_晴天" in msg and "小美" in msg
          and msg.count("喵卡龙") == 1 and "s_晴天、小美" in msg,
          f"n={n} {msg!r}")

    msg, n = await batch_message(["s_晴天", "s_晴天"])
    # 不断言 emoji：喵卡龙不在 cat_food_names 里，默认 emoji 来自 default_gift_emoji
    check("同名同受赠主播合并数量且标注只一行",
          n == 1 and msg.count("送给：s_晴天") == 1
          and "喵卡龙" in msg and "*2个" in msg,
          f"n={n} {msg!r}")

    for name, ok, detail in res:
        print(("PASS " if ok else "FAIL ") + name + ("" if ok else f"   [{detail}]"))
    print("---")
    print("全部通过" if all(r[1] for r in res) else "存在失败项")


if __name__ == "__main__":
    asyncio.run(main())

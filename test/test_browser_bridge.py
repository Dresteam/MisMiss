"""BrowserBridge 基础单元测试（不启动真实浏览器）。"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.browser import BrowserBridge, BrowserConfig, BrowserDisabledError, BrowserSendResult
from core.browser.bridge import _parse_cookies


def test_config_disabled_by_default():
    config = BrowserConfig()
    assert config.enabled is False
    assert config.max_concurrency == 2
    print("PASS 1: 默认关闭")


def test_cookie_parser():
    cookies = _parse_cookies("a=1; b=2=3; broken; c=;")
    assert cookies == [("a", "1"), ("b", "2=3"), ("c", "")], cookies
    print("PASS 2: Cookie 解析")


def test_disabled_send_rejected():
    bridge = BrowserBridge(BrowserConfig())
    try:
        asyncio.run(bridge.send("a=1", 1, "x"))
    except BrowserDisabledError:
        print("PASS 3: 未启用时拒绝发送")
    else:
        raise AssertionError("expected BrowserDisabledError")


def test_result_dataclass():
    result = BrowserSendResult(True, "m1", "x")
    assert result.ok and result.msg_id == "m1"
    print("PASS 4: 结果类型")


if __name__ == "__main__":
    test_config_disabled_by_default()
    test_cookie_parser()
    test_disabled_send_rejected()
    test_result_dataclass()
    print("\n全部通过")

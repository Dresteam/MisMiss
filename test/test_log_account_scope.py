"""日志账户上下文与按账户筛选测试(隔离数据目录)。

覆盖:contextvar 标记与还原、日志条目携带账户名、按账户筛选(全部/面板级/指定账户)、
HTTP /logs/history 的 account 参数。

运行: .venv/Scripts/python.exe test/test_log_account_scope.py
"""
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "web", "backend"))

_TMP_DATA = tempfile.mkdtemp(prefix="mismiss-logacct-test-")
os.environ["MISMISS_DATA_DIR"] = _TMP_DATA

# 必须先初始化 core.logging（它会 _logger.remove()），再导入 ws 注册 sink，
# 与 main.py 的导入顺序一致
from core.logging import (  # noqa: E402
    current_account, get_logger, init, reset_account, set_account,
)
init(log_dir=os.path.join(_TMP_DATA, "logs"), console=False)

from fastapi.testclient import TestClient  # noqa: E402

import web.backend.main as main_mod  # noqa: E402
from api.routes.ws import _buffer  # noqa: E402

_log = get_logger("logacct-test")


def test_contextvar():
    assert current_account.get() == "", "FAIL: 初始应为空（面板级）"
    token = set_account("沅梦")
    assert current_account.get() == "沅梦", "FAIL: set_account 未生效"
    # 嵌套设置与还原
    inner = set_account("测试")
    assert current_account.get() == "测试"
    reset_account(inner)
    assert current_account.get() == "沅梦", "FAIL: 内层还原后应回到外层值"
    reset_account(token)
    assert current_account.get() == "", "FAIL: 还原后应为空"
    print("PASS 1: contextvar 标记 / 嵌套 / 还原正确")


def test_entry_carries_account():
    _log.info("面板级消息")
    t = set_account("沅梦")
    _log.info("沅梦消息")
    reset_account(t)
    t = set_account("测试")
    _log.info("测试消息")
    reset_account(t)
    time.sleep(0.4)  # 等 WS sink 的批量刷入

    entries, _, total = _buffer.get_since(0, 500)
    assert total >= 3, f"FAIL: 条目太少 {total}"
    by_msg = {e["message"]: e["account"] for e in entries if e["message"].endswith("消息")}
    assert by_msg.get("面板级消息") == "", f"FAIL: {by_msg}"
    assert by_msg.get("沅梦消息") == "沅梦", f"FAIL: {by_msg}"
    assert by_msg.get("测试消息") == "测试", f"FAIL: {by_msg}"
    print("PASS 2: 日志条目携带正确的账户名")

    # 筛选语义：None=全部 / [""]=面板级 / [名字]=该账户 / 多元素=并集
    _, _, n_all = _buffer.get_since(0, 500)
    _, _, n_none = _buffer.get_since(0, 500, accounts=None)
    _, _, n_panel = _buffer.get_since(0, 500, accounts=[""])
    _, _, n_ym = _buffer.get_since(0, 500, accounts=["沅梦"])
    assert n_none == n_all, "FAIL: accounts=None 应等于不过滤"
    assert n_ym == 1, f"FAIL: 沅梦应 1 条, 实际 {n_ym}"
    assert n_panel == n_all - 2, f"FAIL: 面板级应为全部减去两条账户日志, {n_panel}/{n_all}"
    print(f"PASS 3: 筛选语义正确（全部 {n_all} / 面板级 {n_panel} / 沅梦 {n_ym}）")

    # 多选：两个账户的并集
    _, _, n_both = _buffer.get_since(0, 500, accounts=["沅梦", "测试"])
    assert n_both == 2, f"FAIL: 两个账户应合计 2 条, 实际 {n_both}"
    # 多选可与「面板级」混选
    _, _, n_mix = _buffer.get_since(0, 500, accounts=["", "沅梦"])
    assert n_mix == n_panel + 1, f"FAIL: 面板级+沅梦 应为 {n_panel + 1}, 实际 {n_mix}"
    # 不存在的账户名不报错，只是筛空
    _, _, n_none_hit = _buffer.get_since(0, 500, accounts=["不存在的账户"])
    assert n_none_hit == 0, f"FAIL: 不存在的账户应为 0 条, 实际 {n_none_hit}"
    # 空列表 ≠ None：空列表是「什么都不要」，不是「不过滤」
    _, _, n_empty = _buffer.get_since(0, 500, accounts=[])
    assert n_empty == 0, f"FAIL: 空列表应为 0 条, 实际 {n_empty}"
    print(f"PASS 3b: 多选筛选正确（沅梦+测试 {n_both} / 面板级+沅梦 {n_mix} / 未知账户 {n_none_hit}）")


def test_api_filter():
    with TestClient(main_mod.app) as client:
        r = client.post("/api/auth/login", json={"username": "MisMiss", "password": "MisMiss"})
        assert r.status_code == 200, f"FAIL: 登录失败 {r.text}"
        h = {"Authorization": f"Bearer {r.json()['token']}"}

        def q(**kw):
            r = client.get("/api/logs/history", headers=h, params={"limit": 200, **kw})
            assert r.status_code == 200, f"FAIL: {r.status_code} {r.text}"
            return r.json()

        all_ = q()
        ym = q(account="沅梦")
        panel = q(account="")
        assert ym["total"] == 1, f"FAIL: {ym['total']}"
        assert ym["entries"][0]["account"] == "沅梦"
        assert panel["total"] == all_["total"] - 2, f"FAIL: {panel['total']}/{all_['total']}"
        # 条目必须带 account 字段，前端筛选依赖它
        assert "account" in all_["entries"][0], "FAIL: 条目缺少 account 字段"
        print("PASS 4: /logs/history 的 account 参数过滤正确")

        # 多选：重复传递同名参数
        both = q(account=["沅梦", "测试"])
        assert both["total"] == 2, f"FAIL: 多选应 2 条, 实际 {both['total']}"
        assert {e["account"] for e in both["entries"]} == {"沅梦", "测试"}, \
            f"FAIL: 多选命中了错误的账户 {[e['account'] for e in both['entries']]}"
        # 多选可与面板级（空串）混选
        mixed = q(account=["", "沅梦"])
        assert mixed["total"] == panel["total"] + 1, \
            f"FAIL: 面板级+沅梦 应为 {panel['total'] + 1}, 实际 {mixed['total']}"
        assert any(e["account"] == "沅梦" for e in mixed["entries"])
        print(f"PASS 4b: 多选筛选正确（两账户 {both['total']} / 混选 {mixed['total']}）")

        # 未认证仍被拦截（新增参数不应绕过鉴权）
        assert client.get("/api/logs/history", params={"account": "沅梦"}).status_code == 401
        print("PASS 5: 未认证访问仍 401")


if __name__ == "__main__":
    test_contextvar()
    test_entry_carries_account()
    test_api_filter()
    print("\n全部通过")

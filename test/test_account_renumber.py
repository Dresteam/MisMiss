"""账户编号：创建不吃号 + 空号重排测试(无外部网络)。

覆盖:
- 用户名重复 / 密码太短 / Cookie 无效 都不会白白消耗一个编号
- Cookie 无效时不留「面板说失败、账户却存在」的幽灵记录
- 重排把编号压紧为 1..N，目录跟着改，两阶段改名不撞车
- 重排后登录令牌里的 account_id 同步改写
- /api/panel/accounts/check-username 不被 /accounts/{account_id} 吞掉
- 用户名可用性查询的返回值

运行: .venv/Scripts/python.exe test/test_account_renumber.py
"""

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

# 必须在 import web.backend.main 之前设好 —— auth.py 与 cookie_login.py
# 都在 import 期就把 _DATA_ROOT 解析成常量,晚设就隔离不掉了。
_TMP = tempfile.mkdtemp(prefix="mismiss-renumber-test-")
os.environ["MISMISS_DATA_DIR"] = _TMP
os.environ["MISMISS_RATE_LIMIT_MIN_INTERVAL"] = "0"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "web", "backend"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient  # noqa: E402

from core.account import AccountManager  # noqa: E402
from core.exceptions import CoreCookieException  # noqa: E402
import web.backend.main as backend  # noqa: E402

# ⚠️ 走 `api.routes` 而不是 `web.backend.api.routes` —— main.py 把 web/backend
# 塞进 sys.path 后按 `api.routes` 导入，同一个文件因此被当作两个模块各执行一次。
from api.routes import auth as auth_route  # noqa: E402

_passed = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global _passed
    if not cond:
        raise AssertionError(f"FAIL: {label} {detail}")
    _passed += 1
    print(f"PASS {_passed}: {label}")


def _assert_isolated() -> None:
    want = Path(_TMP).resolve()
    for where, path in {
        "web.backend.main": Path(backend._DATA_DIR),
        "api.routes.auth": Path(auth_route._DATA_ROOT),
    }.items():
        assert path.resolve() == want, (
            f"数据目录未隔离!{where} 解析为 {path.resolve()},期望 {want}。"
            f"检查环境变量名是否为 MISMISS_DATA_DIR(注意是 MISMISS 不是 MISSISS)。"
        )


async def _make(mgr: AccountManager, want_id: int, name: str) -> int:
    """在指定编号上创建一个账户（模拟历史遗留的空号分布）。"""
    mgr._next_account_id = want_id
    rec = await mgr.create_account(
        name, username=f"u{want_id}", password="pass1234", bot_mode="public"
    )
    return rec.id


# ------------------------------------------------------------------ #
# 1. 创建失败不消耗编号
# ------------------------------------------------------------------ #

async def test_no_id_consumed_on_failure() -> None:
    tmp = tempfile.mkdtemp(prefix="mismiss-noid-")
    mgr = AccountManager(data_dir=tmp)
    mgr.load()

    await _make(mgr, 1, "甲")
    before = mgr._next_account_id

    # 用户名重复
    for _ in range(3):
        try:
            await mgr.create_account("乙", username="u1", password="pass1234",
                                     bot_mode="public")
            raise AssertionError("重复用户名竟然创建成功了")
        except ValueError:
            pass
    check("用户名重复不消耗编号", mgr._next_account_id == before,
          f"{before} -> {mgr._next_account_id}")

    # 密码太短
    try:
        await mgr.create_account("丙", username="u9", password="1", bot_mode="public")
        raise AssertionError("短密码竟然创建成功了")
    except ValueError:
        pass
    check("密码过短不消耗编号", mgr._next_account_id == before)

    # 名称为空
    try:
        await mgr.create_account("  ", username="u8", password="pass1234",
                                 bot_mode="public")
        raise AssertionError("空名称竟然创建成功了")
    except ValueError:
        pass
    check("名称为空不消耗编号", mgr._next_account_id == before)

    # 正常创建仍然用掉一个
    rec = await mgr.create_account("丁", username="u2", password="pass1234",
                                   bot_mode="public")
    check("正常创建使用下一个编号且连续", rec.id == 2 and sorted(mgr._records) == [1, 2],
          f"id={rec.id} ids={sorted(mgr._records)}")


async def test_no_ghost_on_invalid_cookie() -> None:
    """Cookie 无效被拒时，不能留下「面板说失败、账户却存在」的记录。"""
    tmp = tempfile.mkdtemp(prefix="mismiss-ghost-")
    mgr = AccountManager(data_dir=tmp)
    mgr.load()
    await _make(mgr, 1, "甲")
    before = mgr._next_account_id

    async def _boom(*_a, **_kw):
        raise CoreCookieException("Cookie 已过期")

    from core.server import MissevanServer
    original = MissevanServer.create_bot
    MissevanServer.create_bot = _boom  # type: ignore[method-assign]
    try:
        try:
            await mgr.create_account("乙", username="ubad", password="pass1234",
                                     bot_mode="private", cookie="deadbeef")
            raise AssertionError("无效 Cookie 竟然创建成功了")
        except ValueError as e:
            check("无效 Cookie 被拒", "Cookie 无效" in str(e), str(e))
    finally:
        MissevanServer.create_bot = original  # type: ignore[method-assign]

    check("无效 Cookie 不留幽灵记录", sorted(mgr._records) == [1],
          f"残留 {sorted(mgr._records)}")
    check("无效 Cookie 回退编号", mgr._next_account_id == before,
          f"{before} -> {mgr._next_account_id}")
    check("无效 Cookie 不留下数据目录",
          not Path(mgr._server_dirs(before)).exists())
    check("无效 Cookie 后仍可正常创建",
          (await mgr.create_account("丙", username="uok", password="pass1234",
                                    bot_mode="public")).id == before)


# ------------------------------------------------------------------ #
# 2. 重排
# ------------------------------------------------------------------ #

async def test_renumber_compacts_ids() -> None:
    tmp = tempfile.mkdtemp(prefix="mismiss-renum-")
    mgr = AccountManager(data_dir=tmp)
    mgr.load()
    for want in (1, 3, 5, 25):
        await _make(mgr, want, f"账户{want}")
    check("构造出带空号的场景", sorted(mgr._records) == [1, 3, 5, 25],
          str(sorted(mgr._records)))

    before_ids = set(mgr._records)
    before_next = mgr._next_account_id

    dry = await mgr.renumber_accounts(dry_run=True)
    check("dry-run 给出映射", dry["mapping"] == {3: 2, 5: 3, 25: 4}, str(dry["mapping"]))
    check("dry-run 不改记录", set(mgr._records) == before_ids)
    check("dry-run 不改计数器", mgr._next_account_id == before_next)

    res = await mgr.renumber_accounts()
    check("重排后编号连续", sorted(mgr._records) == [1, 2, 3, 4],
          str(sorted(mgr._records)))
    check("计数器指向下一个空位", mgr._next_account_id == 5, str(mgr._next_account_id))
    check("返回的映射与实际一致", res["mapping"] == {3: 2, 5: 3, 25: 4})

    dirs = sorted(p.name for p in Path(mgr._accounts_dir).iterdir())
    check("数据目录跟着改名", dirs == ["1", "2", "3", "4"], str(dirs))
    check("没有临时/孤儿目录残留",
          not [d for d in dirs if "renumber" in d or "orphan" in d], str(dirs))

    # 凭据与配置跟着记录走，没有被错配到别人身上
    check("账户属性跟随编号",
          {r.id: r.username for r in mgr._records.values()}
          == {1: "u1", 2: "u3", 3: "u5", 4: "u25"},
          str({r.id: r.username for r in mgr._records.values()}))

    # 重排后创建的账户接在末尾
    rec = await mgr.create_account("新", username="unew", password="pass1234",
                                   bot_mode="public")
    check("重排后新账户接在末尾", rec.id == 5 and sorted(mgr._records) == [1, 2, 3, 4, 5])


async def test_renumber_noop_when_contiguous() -> None:
    tmp = tempfile.mkdtemp(prefix="mismiss-renum-noop-")
    mgr = AccountManager(data_dir=tmp)
    mgr.load()
    await _make(mgr, 1, "甲")
    await _make(mgr, 2, "乙")
    res = await mgr.renumber_accounts()
    check("编号已连续时无事可做", res["changed"] == 0 and res["mapping"] == {})


# ------------------------------------------------------------------ #
# 3. 令牌 account_id 同步
# ------------------------------------------------------------------ #

async def test_token_remap() -> None:
    tmp = tempfile.mkdtemp(prefix="mismiss-token-remap-")
    mgr = AccountManager(data_dir=tmp)
    mgr.load()
    for want in (1, 3, 5):
        await _make(mgr, want, f"账户{want}")

    # 直接写两个令牌文件：一个指向被重排的账户，一个指向不动的账户
    token_dir = auth_route.TOKEN_DIR
    token_dir.mkdir(parents=True, exist_ok=True)
    moved = "a" * 64
    kept = "b" * 64
    for name, aid in ((moved, 3), (kept, 1)):
        (token_dir / name).write_text(
            json.dumps({"username": "u", "expires": 9e9, "role": "account",
                        "account_id": aid, "must_change_password": False}),
            encoding="utf-8",
        )

    res = await mgr.renumber_accounts()
    changed = auth_route.remap_token_account_ids(res["mapping"])
    check("按映射改写了令牌", changed == 1, f"改了 {changed} 个")

    got_moved = json.loads((token_dir / moved).read_text(encoding="utf-8"))
    got_kept = json.loads((token_dir / kept).read_text(encoding="utf-8"))
    check("被重排账户的令牌指向新编号", got_moved["account_id"] == 2,
          str(got_moved["account_id"]))
    check("未变动账户的令牌原样保留", got_kept["account_id"] == 1)
    check("令牌其余字段未被破坏",
          got_moved["role"] == "account" and got_moved["expires"] == 9e9)


# ------------------------------------------------------------------ #
# 4. HTTP 层：路由顺序与可用性查询
# ------------------------------------------------------------------ #

def test_http_routes() -> None:
    _assert_isolated()
    with TestClient(backend.app) as client:
        r = client.post("/api/auth/login",
                        json={"username": "MisMiss", "password": "MisMiss"})
        assert r.status_code == 200, r.text
        auth = {"Authorization": f"Bearer {r.json()['token']}"}

        # 建两个账户
        for i, uname in enumerate(("alice", "bob")):
            rr = client.post("/api/panel/accounts", json={
                "name": f"账户{i+1}", "bot_mode": "public",
                "username": uname, "password": "pass1234", "duration_days": -1,
            }, headers=auth)
            assert rr.status_code == 200, rr.text

        # check-username 必须命中自己的路由，而不是被 /accounts/{account_id} 吞掉
        rr = client.get("/api/panel/accounts/check-username",
                        params={"username": "alice"}, headers=auth)
        check("check-username 路由未被 account_id 吞掉",
              rr.status_code == 200, f"HTTP {rr.status_code} {rr.text[:120]}")
        check("已占用的用户名报不可用", rr.json()["available"] is False)

        rr = client.get("/api/panel/accounts/check-username",
                        params={"username": "carol"}, headers=auth)
        check("未占用的用户名报可用", rr.json()["available"] is True)

        rr = client.get("/api/panel/accounts/check-username",
                        params={"username": "  "}, headers=auth)
        check("空白用户名报不可用", rr.json()["available"] is False)

        # 重排：先 dry-run 再执行
        rr = client.post("/api/panel/accounts/renumber",
                         params={"dry_run": "true"}, headers=auth)
        check("重排 dry-run 可用", rr.status_code == 200, rr.text[:120])
        check("编号连续时 dry-run 无需改动", rr.json()["changed"] == 0)

        # 造一个空号出来（模拟历史遗留），否则重排无事可做、
        # 也就走不到「改写令牌」那条分支
        from api.deps import get_account_manager
        get_account_manager()._next_account_id = 7
        rr = client.post("/api/panel/accounts", json={
            "name": "账户三", "bot_mode": "public",
            "username": "carol", "password": "pass1234", "duration_days": -1,
        }, headers=auth)
        assert rr.status_code == 200, rr.text
        check("造出空号", rr.json()["id"] == 7, str(rr.json()["id"]))

        rr = client.post("/api/panel/accounts/renumber",
                         params={"dry_run": "true"}, headers=auth)
        check("dry-run 报出待改动数量", rr.json()["changed"] == 1, str(rr.json()))

        rr = client.post("/api/panel/accounts/renumber",
                         params={"dry_run": "false"}, headers=auth)
        check("重排执行可用", rr.status_code == 200, rr.text[:120])
        check("重排返回令牌改写计数", "tokens_updated" in rr.json(), str(rr.json()))
        check("重排后编号连续",
              [a["id"] for a in client.get("/api/panel/accounts",
                                           headers=auth).json()] == [1, 2, 3])


# ------------------------------------------------------------------ #

def main() -> None:
    asyncio.run(test_no_id_consumed_on_failure())
    asyncio.run(test_no_ghost_on_invalid_cookie())
    asyncio.run(test_renumber_compacts_ids())
    asyncio.run(test_renumber_noop_when_contiguous())
    asyncio.run(test_token_remap())
    test_http_routes()
    print(f"\n{_passed}/{_passed} 通过")


if __name__ == "__main__":
    main()

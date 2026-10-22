"""安全修复回归测试（无网络）。

覆盖本轮修复的 7 个问题：

1. SPA 兜底路由的目录穿越（`../` 读面板凭据）
2. 插件 zip 解压 Zip Slip + 插件名白名单
3. `/api/auth/change-password` 与 `/api/auth/skip-first-login` 的角色校验
4. 未 join 的直播间读 `creator_id` 不再 500
5. WS 断线补发取「更新的日志」而不是「更早的日志」
6. `reload_plugin` 保留启用状态
7. 指令参数错误不再打死消息接收循环

运行: .venv/Scripts/python.exe test/test_security_fixes.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import zipfile

# 必须在 import 应用之前设好：auth.py 的令牌目录在 import 期解析
_TMP = tempfile.mkdtemp(prefix="mismiss-security-test-")
os.environ["MISMISS_DATA_DIR"] = _TMP

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "web", "backend"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient  # noqa: E402

import web.backend.main as backend  # noqa: E402
from api.routes.auth import _save_token, token_info  # noqa: E402
from core.command.router import CommandRouter  # noqa: E402
from core.events.bus import EventBus  # noqa: E402
from core.exceptions import CoreApiException  # noqa: E402
from core.plugin.plugin_manager import (  # noqa: E402
    PluginManager,
    _safe_extract_zip,
    _validate_plugin_name,
)
from api.routes.live import _safe_creator_id  # noqa: E402
from api.routes.ws import RingBuffer  # noqa: E402

_passed = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global _passed
    if not cond:
        raise AssertionError(f"FAIL: {label} {detail}")
    _passed += 1
    print(f"PASS {_passed}: {label}")


def _assert_isolated() -> None:
    import api.routes.auth as auth_mod
    check(
        "数据目录已隔离",
        str(auth_mod.AUTH_FILE).startswith(_TMP),
        f"AUTH_FILE={auth_mod.AUTH_FILE}",
    )


# ------------------------------------------------------------------ #
# 1. SPA 兜底目录穿越
# ------------------------------------------------------------------ #

def test_spa_traversal() -> None:
    client = TestClient(backend.app)
    # 正常前端路由仍走 SPA 兜底
    normal = client.get("/logs")
    check("正常前端路由返回 index", normal.status_code == 200)

    # 目录穿越必须被拒。用编码过的 ../，避免客户端提前归一化
    for path in (
        "/%2e%2e%2f%2e%2e%2f%2e%2e%2fdata%2fpanel.json",
        "/..%2f..%2f..%2fconfig.yml",
    ):
        r = client.get(path)
        check(
            f"目录穿越被拒绝 {path[:20]}…",
            r.status_code == 404,
            f"实际 {r.status_code}",
        )
        check(
            "响应体不含面板数据",
            b"next_account_id" not in r.content and b"update:" not in r.content,
        )


# ------------------------------------------------------------------ #
# 2. Zip Slip / 插件名白名单
# ------------------------------------------------------------------ #

def test_zip_slip() -> None:
    tmp = tempfile.mkdtemp(prefix="mismiss-zip-test-")
    evil = os.path.join(tmp, "zip", "evil.txt")
    archive = os.path.join(tmp, "evil.zip")
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("../evil.txt", "pwned")
        zf.writestr("ok/readme.txt", "ok")

    dest = os.path.join(tmp, "out")
    os.makedirs(dest)
    _safe_extract_zip(archive, dest)
    check("Zip Slip 成员未写出目标目录", not os.path.exists(evil))
    check("合法成员正常解压", os.path.exists(os.path.join(dest, "ok", "readme.txt")))

    for bad in ("..", "../x", "a/b", "a\\b", "", "a.b"):
        try:
            _validate_plugin_name(bad)
        except Exception:
            pass
        else:
            raise AssertionError(f"FAIL: 非法插件名被接受: {bad!r}")
    check("插件名白名单拒绝路径字符", True)
    check("中文插件名允许", _validate_plugin_name("签到") == "签到")


# ------------------------------------------------------------------ #
# 3. auth 角色校验
# ------------------------------------------------------------------ #

def test_auth_roles() -> None:
    _assert_isolated()
    client = TestClient(backend.app)
    admin_token = "a" * 64
    account_token = "b" * 64
    _save_token(admin_token, "MisMiss", 9e9, role="admin")
    _save_token(account_token, "user_1", 9e9, role="account", account_id=1)

    # 账户令牌不能改管理员凭据
    r = client.post(
        "/api/auth/change-password",
        json={"token": account_token, "new_password": "hacked"},
    )
    check("账户令牌改管理员密码被拒", r.status_code == 403, f"实际 {r.status_code}")

    # skip-first-login 匿名不可用
    r = client.post("/api/auth/skip-first-login")
    check("匿名 skip-first-login 被拒", r.status_code == 401, f"实际 {r.status_code}")
    r = client.post(
        "/api/auth/skip-first-login",
        headers={"Authorization": f"Bearer {account_token}"},
    )
    check("账户令牌 skip-first-login 被拒", r.status_code == 403, f"实际 {r.status_code}")

    # 管理员令牌可以（首次登录免原密码）
    r = client.post(
        "/api/auth/skip-first-login",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    check("管理员 skip-first-login 通过", r.status_code == 200, f"实际 {r.status_code}")
    check("令牌仍可解析", token_info(admin_token) is not None)


# ------------------------------------------------------------------ #
# 4. 未 join 的直播间
# ------------------------------------------------------------------ #

def test_safe_creator_id() -> None:
    class NotJoined:
        @property
        def creator_id(self):
            raise CoreApiException("直播间尚未初始化")

    check("creator_id 异常时返回 0", _safe_creator_id(NotJoined()) == 0)

    class Joined:
        creator_id = 42

    check("creator_id 正常时原样返回", _safe_creator_id(Joined()) == 42)


# ------------------------------------------------------------------ #
# 5. WS 断线补发方向
# ------------------------------------------------------------------ #

def test_ws_gap_direction() -> None:
    buf = RingBuffer(capacity=10)
    for i in range(5):
        buf.append("INFO", f"line-{i}", "test", "/tmp/test.py")

    newer = buf.get_after(2, limit=10)
    check("get_after 返回更新的日志", [e["message"] for e in newer] == [
        "line-2", "line-3", "line-4",
    ], str(newer))
    older, _, _ = buf.get_since(3, limit=10)
    check("get_since 仍返回更早的日志", [e["message"] for e in older] == [
        "line-0", "line-1",
    ], str(older))


# ------------------------------------------------------------------ #
# 6. reload 保留启用状态
# ------------------------------------------------------------------ #

def test_reload_keeps_enabled() -> None:
    async def main() -> None:
        tmp = tempfile.mkdtemp(prefix="mismiss-reload-test-")
        plugin_dir = os.path.join(tmp, "plugins")
        demo = os.path.join(plugin_dir, "demo")
        os.makedirs(demo)
        with open(os.path.join(demo, "metadata.yaml"), "w", encoding="utf-8") as f:
            f.write(
                "name: demo\nauthor: tester\ndesc: 测试\ndescription: 测试\n"
                "version: 1.0.0\n"
            )
        with open(os.path.join(demo, "main.py"), "w", encoding="utf-8") as f:
            f.write(
                "from interfaces.plugin import Plugin\n\n"
                "class Demo(Plugin):\n"
                "    async def initialize(self, config):\n"
                "        pass\n"
            )

        pm = PluginManager(
            plugin_dir=plugin_dir,
            event_bus=EventBus(),
            config_dir=os.path.join(tmp, "config"),
            permission_dir=os.path.join(tmp, "permissions"),
            plugin_data_dir=os.path.join(tmp, "data"),
        )
        await pm.load_all()
        await pm.enable_plugin("demo")
        check("插件已启用", pm.get_plugin("demo").enabled is True)

        await pm.reload_plugin("demo")
        check(
            "reload 后仍保持启用",
            pm.get_plugin("demo").enabled is True,
            str(pm.get_plugin("demo").enabled),
        )

    asyncio.run(main())


# ------------------------------------------------------------------ #
# 7. 指令参数错误不打断消息循环
# ------------------------------------------------------------------ #

def test_command_bad_args() -> None:
    bus = EventBus()
    router = CommandRouter(bus)

    from interfaces.command import command
    from interfaces.plugin import Plugin

    class Demo(Plugin):
        def __init__(self) -> None:
            super().__init__({})

        @command("echo")
        def echo(self, text: str) -> None:
            raise AssertionError("不应执行到缺参的指令")

    Demo.name = "demo"
    plugin = Demo()
    router.register_plugin(plugin)

    class Msg:
        message = "echo"

    try:
        router._listener.on_message(Msg())  # type: ignore[arg-type]
    except Exception as e:
        raise AssertionError(f"FAIL: 缺参指令把异常抛出了: {e}")
    check("缺参指令只记录不抛出", True)

    router.unregister_plugin(plugin)


def main() -> None:
    _assert_isolated()
    test_spa_traversal()
    test_zip_slip()
    test_auth_roles()
    test_safe_creator_id()
    test_ws_gap_direction()
    test_reload_keeps_enabled()
    test_command_bad_args()
    print("\n全部通过")


if __name__ == "__main__":
    main()

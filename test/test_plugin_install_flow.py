"""插件库安装/更新版本流程测试(无网络)。

锁住前端依赖的响应契约——此前前端按下状态码判定,把两个方向都用反了:

- 上传**更高**版本 → 200 + ``action=update``(仅返回信号,尚未安装,等用户确认)
- 上传**相同/更低**版本 → 409 + ``detail``(拒绝,不是更新信号)
- ``/install/update`` 必须同样拒绝降级覆盖,否则它就是绕过 ``/install`` 版本校验的后门

运行: .venv/Scripts/python.exe test/test_plugin_install_flow.py
"""
import io
import os
import shutil
import sys
import tempfile
import zipfile

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "src"))

os.environ["MISMISS_DATA_DIR"] = tempfile.mkdtemp(prefix="mismiss-install-flow-")

from fastapi.testclient import TestClient  # noqa: E402
from web.backend.main import app  # noqa: E402  （导入时会 chdir 到项目根）

# 库级 PluginManager 的 plugin_dir 是相对路径 "plugins"，chdir 到临时目录即可隔离，
# 避免测试往真实仓库的 plugins/ 里装东西
_WORK = tempfile.mkdtemp(prefix="mismiss-lib-")
os.makedirs(os.path.join(_WORK, "plugins"), exist_ok=True)
os.chdir(_WORK)

res = []


def check(name: str, cond: bool, detail: str = "") -> None:
    res.append((name, cond, detail))


def _zip(name: str, version: str) -> bytes:
    """构造真实布局的插件包：成员位于顶层目录 <name>/ 之下。"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(
            f"{name}/metadata.yaml",
            f"name: {name}\ndesc: 流程测试\nauthor: test\nversion: {version}\n",
        )
        z.writestr(
            f"{name}/main.py",
            "from interfaces.plugin import Plugin\n\n\n"
            "class Demo(Plugin):\n"
            "    pass\n",
        )
    return buf.getvalue()


def _upload(c, H, url: str, name: str, version: str):
    return c.post(
        url, headers=H,
        files={"file": (f"{name}.zip", _zip(name, version), "application/zip")},
    )


def _lib_version(c, H, name: str) -> str | None:
    items = c.get("/api/plugin/list", headers=H).json()
    return next((p["version"] for p in items if p["name"] == name), None)


with TestClient(app) as c:
    token = c.post(
        "/api/auth/login",
        json={"username": "MisMiss", "password": "MisMiss"},
    ).json()["token"]
    H = {"Authorization": f"Bearer {token}"}

    # 基线:装一个 1.0.0 进库
    r = _upload(c, H, "/api/plugin/install", "zz_demo", "1.0.0")
    check("首次安装 → 200", r.status_code == 200 and r.json().get("plugin") == "zz_demo",
          f"{r.status_code} {r.text[:120]}")

    # ---- 1. 相同版本 → 409 拒绝,且响应体是 detail 而非版本信息 ----
    r = _upload(c, H, "/api/plugin/install", "zz_demo", "1.0.0")
    body = r.json()
    check("相同版本 → 409 拒绝", r.status_code == 409, f"{r.status_code} {body}")
    check("拒绝响应为 detail(不含 old_version/new_version)",
          "detail" in body and "old_version" not in body, f"{body}")

    # ---- 2. 更低版本 → 409 拒绝 ----
    r = _upload(c, H, "/api/plugin/install", "zz_demo", "0.9.0")
    check("更低版本 → 409 拒绝", r.status_code == 409, f"{r.status_code}")

    # ---- 3. 更高版本 → 200 + action=update + 两个版本号（此时尚未安装） ----
    r = _upload(c, H, "/api/plugin/install", "zz_demo", "1.1.0")
    body = r.json()
    check("更高版本 → 200 且 action=update",
          r.status_code == 200 and body.get("action") == "update", f"{r.status_code} {body}")
    check("携带 old_version / new_version",
          body.get("old_version") == "1.0.0" and body.get("new_version") == "1.1.0", f"{body}")
    check("返回信号时尚未真正安装", _lib_version(c, H, "zz_demo") == "1.0.0",
          f"库中版本 {_lib_version(c, H, 'zz_demo')}")

    # ---- 4. /install/update 拒绝降级覆盖（堵住绕过 /install 校验的后门） ----
    r = _upload(c, H, "/api/plugin/install/update", "zz_demo", "1.0.0")
    check("/install/update 相同版本 → 409", r.status_code == 409, f"{r.status_code} {r.text[:120]}")
    r = _upload(c, H, "/api/plugin/install/update", "zz_demo", "0.9.0")
    check("/install/update 更低版本 → 409", r.status_code == 409, f"{r.status_code}")
    check("被拒后库中版本未变", _lib_version(c, H, "zz_demo") == "1.0.0",
          f"库中版本 {_lib_version(c, H, 'zz_demo')}")

    # ---- 5. /install/update 更高版本 → 真正覆盖 ----
    r = _upload(c, H, "/api/plugin/install/update", "zz_demo", "1.1.0")
    check("/install/update 更高版本 → 200", r.status_code == 200, f"{r.status_code} {r.text[:120]}")
    check("库中版本已更新为 1.1.0", _lib_version(c, H, "zz_demo") == "1.1.0",
          f"库中版本 {_lib_version(c, H, 'zz_demo')}")

    # ---- 6. 全新插件不受版本校验影响 ----
    r = _upload(c, H, "/api/plugin/install", "zz_other", "0.1.0")
    check("全新插件正常安装", r.status_code == 200 and _lib_version(c, H, "zz_other") == "0.1.0",
          f"{r.status_code} {r.text[:120]}")

# 确认没有污染真实仓库
_real_plugins = os.path.join(_ROOT, "plugins")
_leaked = [d for d in ("zz_demo", "zz_other") if os.path.isdir(os.path.join(_real_plugins, d))]
check("未污染真实 plugins/ 目录", not _leaked, f"泄漏: {_leaked}")

for name, ok, detail in res:
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else f"   [{detail}]"))
print("---")
print("全部通过" if all(r[1] for r in res) else "存在失败项")

shutil.rmtree(_WORK, ignore_errors=True)

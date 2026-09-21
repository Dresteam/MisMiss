"""config.yml 写入失败时的报错与数据保护测试（无网络）。

背景：Docker 部署曾把 config.yml 以只读(:ro)方式挂载，而面板的四个设置端点
都要写回这个文件。写入抛出的 PermissionError 没有被捕获，面板只看到无信息的
500，用户无从判断是自己填错了还是部署方式不对。

本测试锁住三件事：
1. 写入失败时返回**带 detail 的可读报错**，而不是裸 500
2. 读取失败时**不能**拿空字典覆盖写回 —— 那会把文件里其余配置全部抹掉
3. 成功写入时保留其余配置段与键序

运行： .venv/Scripts/python.exe test/test_config_write_guard.py
"""
import os
import stat
import sys
import tempfile
from pathlib import Path

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "src"))

os.environ["MISMISS_DATA_DIR"] = tempfile.mkdtemp(prefix="mismiss-cfgwrite-")

import yaml  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from web.backend.main import app  # noqa: E402
from api.routes import config as cfgmod  # noqa: E402
from api.routes import update as upd  # noqa: E402

res: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    res.append((name, cond, detail))


SAMPLE = """\
server:
  data_dir: data
  api_port: 18080
bot:
  timer_interval: 120
logging:
  dir: logs
  level: INFO
update:
  repo: Dresteam/MisMiss
  mirror: ''
"""

_tmp = Path(tempfile.mkdtemp(prefix="mismiss-cfg-file-"))
_cfg = _tmp / "config.yml"

# 两个模块各自持有一份路径常量，测试里一起改到临时文件上
_orig_paths = (cfgmod._CONFIG_PATH, upd._CONFIG_PATH)
cfgmod._CONFIG_PATH = str(_cfg)
upd._CONFIG_PATH = _cfg


def _write_sample() -> None:
    _cfg.write_text(SAMPLE, encoding="utf-8")


def _set_readonly(ro: bool) -> None:
    _cfg.chmod(stat.S_IREAD if ro else stat.S_IWRITE | stat.S_IREAD)


try:
    with TestClient(app) as c:
        tok = c.post(
            "/api/auth/login", json={"username": "MisMiss", "password": "MisMiss"},
        ).json()["token"]
        H = {"Authorization": f"Bearer {tok}"}

        # ---- 1. 可写时：三个端点都能存，且不丢其余配置 ----
        _write_sample()
        r = c.put("/api/config/log-level", headers=H, json={"level": "DEBUG"})
        check("log-level 正常保存 -> 200", r.status_code == 200,
              f"{r.status_code} {r.text[:100]}")

        r = c.post("/api/update/settings", headers=H, json={
            "repo": "Dresteam/MisMiss", "mirror": "https://gh-proxy.com/",
            "proxy": "", "notify_enabled": True,
            "notify_before": "  即将更新  ", "notify_after": "已更新完成",
        })
        check("update/settings 正常保存 -> 200", r.status_code == 200,
              f"{r.status_code} {r.text[:100]}")

        data = yaml.safe_load(_cfg.read_text(encoding="utf-8"))
        check("保存后其余配置段仍在",
              all(k in data for k in ("server", "bot", "logging", "update")),
              str(list(data.keys())))
        check("日志等级已落盘", data.get("logging", {}).get("level") == "DEBUG",
              str(data.get("logging")))
        check("更新提示已落盘且入库前被裁剪",
              data["update"].get("notify_enabled") is True
              and data["update"].get("notify_before") == "即将更新",
              str(data["update"]))
        check("键序未被 sort_keys 打乱",
              list(data.keys()) == ["server", "bot", "logging", "update"],
              str(list(data.keys())))

        # ---- 2. 只读时：三个端点都要给可读报错，而不是裸 500 ----
        _write_sample()
        before = _cfg.read_text(encoding="utf-8")
        _set_readonly(True)
        try:
            for label, call in (
                ("log-level", lambda: c.put(
                    "/api/config/log-level", headers=H, json={"level": "INFO"})),
                ("ports", lambda: c.put(
                    "/api/config/ports", headers=H, json={"api_port": 18099})),
                ("update/settings", lambda: c.post(
                    "/api/update/settings", headers=H, json={"repo": "a/b"})),
            ):
                r = call()
                body = r.json()
                detail = body.get("detail", "")
                check(f"只读时 {label} 返回可读报错",
                      r.status_code == 500 and "不可写" in detail,
                      f"{r.status_code} {str(body)[:120]}")
                check(f"只读时 {label} 的报错带路径",
                      str(_cfg) in detail, detail[:120])
        finally:
            _set_readonly(False)
        check("写入失败不修改原文件", _cfg.read_text(encoding="utf-8") == before,
              "文件被改动了")

        # ---- 3. 文件损坏时：报错而不是把配置抹成空 ----
        _write_sample()
        good = _cfg.read_text(encoding="utf-8")
        _cfg.write_text("server: [未闭合\n", encoding="utf-8")
        r = c.post("/api/update/settings", headers=H, json={"repo": "a/b"})
        check("配置解析失败时返回 500 而非静默覆盖",
              r.status_code == 500, f"{r.status_code} {r.text[:100]}")
        check("解析失败时文件未被覆盖成只含 update 段",
              _cfg.read_text(encoding="utf-8") == "server: [未闭合\n",
              _cfg.read_text(encoding="utf-8")[:60])

        # 注：不测端口端点的「写成功」路径 —— 它会在 0.5s 后调 os.execv 重启进程，
        # 在测试里执行等于把测试进程替换掉。它的失败路径已由上面第 2 组覆盖。
finally:
    cfgmod._CONFIG_PATH, upd._CONFIG_PATH = _orig_paths
    _set_readonly(False)

# ---------------------------------------------------------------- #

passed = sum(1 for _, ok, _ in res if ok)
for i, (name, ok, detail) in enumerate(res, 1):
    print(f"{'PASS' if ok else 'FAIL'} {i}: {name}" + (f"  [{detail}]" if not ok else ""))
print(f"\n{passed}/{len(res)} 通过")
sys.exit(0 if passed == len(res) else 1)

"""插件批量推送 / 默认插件功能测试(无网络)。

- **批量推送**：只更新「已安装且副本版本低于库」的账户；已是最新的跳过、
  未安装的不动、库中不存在的插件报 404。
- **默认插件**：清单持久化到 panel.json；新建账户自动安装并启用；
  `apply_default_plugins` 补齐存量账户；装不上的只告警不影响账户创建。

运行: .venv/Scripts/python.exe test/test_plugin_push_defaults.py
"""
import asyncio
import json
import os
import shutil
import sys
import tempfile

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "src"))

sys.stdout.reconfigure(errors="replace")

from core.account import AccountManager  # noqa: E402
from core.exceptions import CorePluginNotFoundException  # noqa: E402

LIB_VERSION = "1.1.0"
OLD_VERSION = "1.0.0"

_MAIN_PY = """\
from __future__ import annotations

from interfaces.plugin import Plugin


class Demo(Plugin):
    async def initialize(self, config) -> None:
        self.ready = True
"""

res: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    res.append((name, cond, detail))


def _write_library_plugin(lib: str, name: str, version: str) -> None:
    d = os.path.join(lib, name)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "metadata.yaml"), "w", encoding="utf-8") as f:
        f.write(f"name: {name}\ndesc: 推送测试\nauthor: test\nversion: {version}\n")
    with open(os.path.join(d, "main.py"), "w", encoding="utf-8") as f:
        f.write(_MAIN_PY)
    # 带 schema 才会生成 {name}_config.json（无 schema 时默认值为空、不落盘）
    with open(os.path.join(d, "_conf_schema.json"), "w", encoding="utf-8") as f:
        json.dump({"greeting": {"type": "string", "default": "hi", "description": "问候"}}, f)


async def main() -> None:
    # 库级 PluginManager 用的是相对路径 "plugins"，chdir 到临时目录即可隔离
    work = tempfile.mkdtemp(prefix="mismiss-push-")
    lib = os.path.join(work, "plugins")
    os.makedirs(lib, exist_ok=True)
    _write_library_plugin(lib, "zz_push", LIB_VERSION)
    os.chdir(work)

    mgr = AccountManager(data_dir=os.path.join(work, "data"))
    mgr.load()
    # 生产路径由 start_all() 扫描插件库；本测试直接建账户，故显式加载
    await mgr.get_library_pm().load_all()

    async def new_account(name: str) -> int:
        rec = await mgr.create_account(name, username=f"u_{name}", password="pw12")
        return rec.id

    # ---- 1. 准备三种账户：副本落后 / 副本已最新 / 未安装 ----
    a_out = await new_account("落后")
    a_ok = await new_account("最新")
    a_none = await new_account("未装")

    await mgr.install_plugin_to_account(a_out, "zz_push")
    await mgr.install_plugin_to_account(a_ok, "zz_push")

    def meta_of(aid: int):
        return mgr.get_server(aid)._plugin_manager.get_plugin("zz_push")

    # 模拟账户副本版本落后（直接改元数据版本号，避免手工改文件的时序问题）
    meta_of(a_out).version = OLD_VERSION
    check("前置：账户副本版本已置为落后",
          meta_of(a_out).version == OLD_VERSION, meta_of(a_out).version)
    check("前置：账户未安装该插件", meta_of(a_none) is None)

    # ---- 2. 推送单个插件 ----
    result = await mgr.push_plugin_to_accounts("zz_push")
    check("落后账户被更新", any("落后" in s for s in result["updated"]), f"{result['updated']}")
    check("最新账户被跳过", any("最新" in s for s in result["skipped"]), f"{result['skipped']}")
    check("未安装账户不受影响",
          not any("未装" in s for s in result["updated"] + result["skipped"]),
          f"{result}")
    check("推送后副本版本已对齐库",
          meta_of(a_out).version == LIB_VERSION, meta_of(a_out).version)

    # ---- 3. 再推一次：此时全部已最新 ----
    result = await mgr.push_plugin_to_accounts("zz_push")
    check("再推送无更新（全部跳过）",
          result["updated"] == [] and len(result["skipped"]) == 2, f"{result}")

    # ---- 4. 库里没有的插件 → 抛异常 ----
    try:
        await mgr.push_plugin_to_accounts("zz_not_exist")
        check("推送不存在的插件抛异常", False, "未抛出")
    except CorePluginNotFoundException:
        check("推送不存在的插件抛异常", True)

    # ---- 5. 默认插件：切换 + 持久化 ----
    defaults = mgr.set_plugin_default("zz_push", True)
    check("默认清单已加入", defaults == ["zz_push"], f"{defaults}")
    panel = json.load(open(os.path.join(work, "data", "panel.json"), encoding="utf-8"))
    check("默认清单已落盘 panel.json",
          panel.get("default_plugins") == ["zz_push"], f"{panel.get('default_plugins')}")

    mgr2 = AccountManager(data_dir=os.path.join(work, "data"))
    mgr2.load()
    check("重新载入后默认清单保留",
          mgr2.list_default_plugins() == ["zz_push"], f"{mgr2.list_default_plugins()}")

    # ---- 6. 新建账户自动安装并启用默认插件 ----
    a_new = await new_account("新建")
    m = mgr.get_server(a_new)._plugin_manager.get_plugin("zz_push")
    check("新建账户已自动安装默认插件", m is not None)
    check("新建账户默认插件已启用", bool(m and m.enabled), f"{m and m.enabled}")

    # ---- 7. 补齐存量账户 ----
    apply_res = await mgr.apply_default_plugins()
    check("补齐应用到存量账户",
          "未装" in apply_res["applied"] and apply_res["applied"]["未装"] == ["zz_push"],
          f"{apply_res['applied']}")
    check("已装账户也一并启用",
          meta_of(a_none) is not None and meta_of(a_none).enabled,
          f"{meta_of(a_none) and meta_of(a_none).enabled}")

    # ---- 8. 默认插件在库中不存在时：不阻断账户创建 ----
    mgr.set_plugin_default("zz_ghost", True)
    a_ghost = await new_account("幽灵")
    check("库中不存在的默认插件不阻断账户创建",
          mgr.get_record(a_ghost) is not None)
    apply_res = await mgr.apply_default_plugins()
    check("补齐结果报告库中缺失的默认插件",
          "zz_ghost" in apply_res["failed"], f"{apply_res['failed']}")

    # ---- 9. 取消默认 ----
    check("取消默认后清单为空",
          mgr.set_plugin_default("zz_ghost", False) == ["zz_push"],
          f"{mgr.list_default_plugins()}")

    # ---- 10. 账户端一键更新（范围限定在单个账户，同一套版本守卫） ----
    # 先清空默认清单，否则新建账户会自动装上 zz_push，测不出「未安装」的分支
    mgr.set_plugin_default("zz_push", False)

    b_out = await new_account("单账户落后")
    b_ok = await new_account("单账户最新")
    await mgr.install_plugin_to_account(b_out, "zz_push")
    await mgr.install_plugin_to_account(b_ok, "zz_push")
    mgr.get_server(b_out)._plugin_manager.get_plugin("zz_push").version = OLD_VERSION

    res_single = await mgr.update_plugins_in_account(b_out)
    check("单账户一键更新：落后的被更新",
          res_single["updated"] == ["zz_push"], f"{res_single}")
    check("单账户一键更新：副本已对齐库版本",
          meta_of(b_out).version == LIB_VERSION, meta_of(b_out).version)

    res_single = await mgr.update_plugins_in_account(b_out)
    check("单账户一键更新：已最新则空更新",
          res_single["updated"] == [] and res_single["skipped"] == ["zz_push"],
          f"{res_single}")

    res_single = await mgr.update_plugins_in_account(b_ok)
    check("单账户一键更新：不影响其他账户（各自独立）",
          res_single["updated"] == [], f"{res_single}")

    # 未安装任何插件的账户 → 无事发生
    b_none = await new_account("单账户未装")
    res_single = await mgr.update_plugins_in_account(b_none)
    check("单账户一键更新：未安装则空更新",
          res_single["updated"] == [] and res_single["skipped"] == []
          and res_single["failed"] == [] and res_single["groups"] == [],
          f"{res_single}")

    # dry_run 预览：只算不做，并给出按插件的版本跨度
    mgr.get_server(b_ok)._plugin_manager.get_plugin("zz_push").version = OLD_VERSION
    preview = await mgr.update_plugins_in_account(b_ok, dry_run=True)
    check("账户一键更新 dry_run 列出将更新的插件",
          preview["updated"] == ["zz_push"], f"{preview['updated']}")
    check("账户一键更新 dry_run ⽿改动副本",
          meta_of(b_ok).version == OLD_VERSION, meta_of(b_ok).version)
    check("账户一键更新 dry_run 给出版本跨度",
          preview["groups"] == [
              {"label": "zz_push", "items": [f"v{OLD_VERSION} → v{LIB_VERSION}"]}
          ],
          f"{preview.get('groups')}")
    check("账户一键更新 dry_run 置 dry_run=True",
          preview.get("dry_run") is True, f"{preview.get('dry_run')}")

    real1 = await mgr.update_plugins_in_account(b_ok, dry_run=False)
    check("账户一键更新实推后副本对齐",
          meta_of(b_ok).version == LIB_VERSION and real1.get("dry_run") is False,
          f"{meta_of(b_ok).version} / {real1.get('dry_run')}")
    check("实推后同样带版本跨度",
          real1["groups"] == [
              {"label": "zz_push", "items": [f"v{OLD_VERSION} → v{LIB_VERSION}"]}
          ],
          f"{real1.get('groups')}")

    # 账户不存在 → 抛异常
    from core.exceptions import CoreAccountNotFoundException
    try:
        await mgr.update_plugins_in_account(999999)
        check("单账户一键更新：账户不存在抛异常", False, "未抛出")
    except CoreAccountNotFoundException:
        check("单账户一键更新：账户不存在抛异常", True)

    # ---- 11. dry_run 预览：只算不做 ----
    c_out = await new_account("预览落后")
    await mgr.install_plugin_to_account(c_out, "zz_push")
    mgr.get_server(c_out)._plugin_manager.get_plugin("zz_push").version = OLD_VERSION

    preview = await mgr.push_plugin_to_accounts("zz_push", dry_run=True)
    check("dry_run 标出将更新的条目",
          any("预览落后" in s for s in preview["updated"]), f"{preview['updated']}")
    check("dry_run 置 dry_run=True", preview.get("dry_run") is True, f"{preview.get('dry_run')}")
    check("dry_run 不改动副本版本",
          meta_of(c_out).version == OLD_VERSION, meta_of(c_out).version)

    real = await mgr.push_plugin_to_accounts("zz_push", dry_run=False)
    check("实推后副本被更新",
          any("预览落后" in s for s in real["updated"]) and meta_of(c_out).version == LIB_VERSION,
          f"{real['updated']} / {meta_of(c_out).version}")
    check("实推后 dry_run=False", real.get("dry_run") is False, f"{real.get('dry_run')}")

    # 默认插件补齐的 dry_run
    mgr.set_plugin_default("zz_push", True)
    d_none = await new_account("预览未装")   # 默认开着 → 会自动装上
    mgr.set_plugin_default("zz_push", False)
    # 人为卸载掉，制造「需要补齐」的状态
    await mgr.uninstall_plugin_from_account(d_none, "zz_push", delete_config=True, delete_data=True)
    mgr.set_plugin_default("zz_push", True)

    d_preview = await mgr.apply_default_plugins(dry_run=True)
    check("默认插件 dry_run 列出将补齐的账户",
          d_preview["applied"].get("预览未装") == ["zz_push"], f"{d_preview['applied']}")
    check("默认插件 dry_run 不真的装上",
          mgr.get_server(d_none)._plugin_manager.get_plugin("zz_push") is None)
    check("默认插件 dry_run 置 dry_run=True",
          d_preview.get("dry_run") is True, f"{d_preview.get('dry_run')}")

    d_real = await mgr.apply_default_plugins(dry_run=False)
    check("默认插件实补后已装上并启用",
          (lambda m: m is not None and m.enabled)(
              mgr.get_server(d_none)._plugin_manager.get_plugin("zz_push")),
          f"{mgr.get_server(d_none)._plugin_manager.get_plugin('zz_push')}")

    # dry_run 预览应为空的情形
    mgr.set_plugin_default("zz_push", False)
    empty = await mgr.push_plugin_to_accounts("zz_push", dry_run=True)
    check("全部最新时 dry_run 的 updated 为空",
          empty["updated"] == [] and empty["skipped"], f"{empty}")

    # ---- 12. 卸载时的配置 / 权限 / 数据清理 ----
    u = await new_account("卸载测试")
    await mgr.install_plugin_to_account(u, "zz_push")
    base = mgr._server_dirs(u)
    cfg_path = os.path.join(base, "config", "zz_push_config.json")
    perm_path = os.path.join(base, "permissions", "zz_push_permissions.json")
    data_dir = os.path.join(base, "plugins", "zz_push")

    check("卸载前：配置文件已生成", os.path.isfile(cfg_path), cfg_path)
    check("卸载前：权限文件已生成", os.path.isfile(perm_path), perm_path)

    def seed_data_dir() -> None:
        """造混合数据：JSON（self.data 数据）与非 JSON（其他持久化文件），含子目录。"""
        shutil.rmtree(data_dir, ignore_errors=True)
        os.makedirs(os.path.join(data_dir, "sub"), exist_ok=True)
        for rel in ("state.json", "sub/nested.json", "cache.db", "sub/log.txt"):
            with open(os.path.join(data_dir, *rel.split("/")), "w", encoding="utf-8") as f:
                f.write("{}")

    def exists(*parts: str) -> bool:
        return os.path.exists(os.path.join(data_dir, *parts))

    async def uninstall(**flags) -> None:
        await mgr.uninstall_plugin_from_account(u, "zz_push", **flags)

    # 只删「插件数据」(JSON) → 非 JSON 保留
    seed_data_dir()
    await uninstall(delete_config=False, delete_data=True, delete_persistent=False)
    check("delete_data → 顶层 JSON 已删", not exists("state.json"))
    check("delete_data → 子目录 JSON 已删", not exists("sub", "nested.json"))
    check("delete_data → 非 JSON 保留", exists("cache.db") and exists("sub", "log.txt"))

    # 只删「持久化数据」(非 JSON) → JSON 保留
    seed_data_dir()
    await uninstall(delete_config=False, delete_data=False, delete_persistent=True)
    check("delete_persistent → 非 JSON 已删",
          not exists("cache.db") and not exists("sub", "log.txt"))
    check("delete_persistent → JSON 保留",
          exists("state.json") and exists("sub", "nested.json"))

    # 只含 JSON 的子目录：删空后应被回收，整个数据目录也一并消失
    shutil.rmtree(data_dir, ignore_errors=True)
    os.makedirs(os.path.join(data_dir, "only_json"), exist_ok=True)
    with open(os.path.join(data_dir, "only_json", "a.json"), "w", encoding="utf-8") as f:
        f.write("{}")
    await uninstall(delete_config=False, delete_data=True, delete_persistent=False)
    check("只含 JSON 的子目录被回收", not os.path.isdir(os.path.join(data_dir, "only_json")))
    check("数据目录空了也一并回收", not os.path.isdir(data_dir), data_dir)

    # 两个都不勾 → 目录原样保留（重装即可续用）
    seed_data_dir()
    await uninstall(delete_config=False, delete_data=False, delete_persistent=False)
    check("都不勾选 → 数据目录原样保留",
          exists("state.json") and exists("cache.db") and exists("sub", "nested.json"))
    check("都不勾选 → 配置文件保留", os.path.isfile(cfg_path), cfg_path)
    check("都不勾选 → 权限文件保留", os.path.isfile(perm_path), perm_path)

    # 全勾 → 清干净
    seed_data_dir()
    await uninstall(delete_config=True, delete_data=True, delete_persistent=True)
    check("全勾选 → 配置文件已删", not os.path.exists(cfg_path), cfg_path)
    check("全勾选 → 权限文件已删", not os.path.exists(perm_path), perm_path)
    check("全勾选 → 数据目录已删", not os.path.isdir(data_dir), data_dir)
    check("源码副本已删",
          not os.path.isdir(os.path.join(base, "installed_plugins", "zz_push")))

    await mgr.shutdown_all()
    for name, ok, detail in res:
        print(("PASS " if ok else "FAIL ") + name + ("" if ok else f"   [{detail}]"))
    print("---")
    print("全部通过" if all(r[1] for r in res) else "存在失败项")
    shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    asyncio.run(main())

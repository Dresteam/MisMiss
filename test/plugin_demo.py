"""插件系统演示。

展示 PluginManager 的全部功能：
1. 扫描并加载插件
2. 查看插件列表和元数据（含 plugin_id / short_desc / repo / display_name）
3. 查看插件事件处理器
4. 查看插件 README / CHANGELOG
5. 禁用和启用插件（start / stop 别名）
6. 重载插件
7. 配置管理（_conf_schema.json 默认值 + 读写）
8. 权限管理（_permission.json 默认值 + 读写）
9. 插件数据目录（data_dir 创建 / 写入 / 清理）
10. 模拟事件触发验证
"""

from __future__ import annotations

import sys
from pathlib import Path

# 确保 src/ 在路径中
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from core.events import EventBus
from core.plugin import PluginManager, PluginConfigManager, PluginPermissionManager
from interfaces.plugin import Plugin
from core.exceptions import (
    CorePluginNotFoundException,
)


def banner(title: str) -> None:
    """打印分隔标题。"""
    print()
    print("=" * 60)
    print(f"  {title}")
    print("=" * 60)


def main() -> None:
    banner("MisMiss Plugin System Demo")

    # 项目根目录
    project_root = Path(__file__).resolve().parent.parent
    plugin_dir = str(project_root / "plugins")
    config_dir = str(project_root / "data" / "config")
    perm_dir = str(project_root / "data" / "permissions")
    data_dir = str(project_root / "data")

    # ================================================================ #
    # 1. 初始化
    # ================================================================ #
    banner("[1] Initialize PluginManager")
    event_bus = EventBus()
    pm = PluginManager(
        plugin_dir=plugin_dir,
        event_bus=event_bus,
        config_dir=config_dir,
        permission_dir=perm_dir,
        plugin_data_dir=data_dir,
    )
    print(f"    plugin_dir : {plugin_dir}")
    print(f"    config_dir : {config_dir}")
    print(f"    perm_dir   : {perm_dir}")
    print(f"    data_dir   : {data_dir}")

    # ================================================================ #
    # 2. 加载所有插件
    # ================================================================ #
    banner("[2] Load all plugins")
    import asyncio

    async def _load():
        await pm.load_all()

    asyncio.run(_load())

    # ================================================================ #
    # 3. 查看插件列表（含新 metadata 字段）
    # ================================================================ #
    banner("[3] Plugin list (with new metadata fields)")
    plugins = pm.list_plugins()
    if not plugins:
        print("    (no plugins)")
        print()
        print("[!] Hint: ensure plugins/example_plugin/ exists with main.py and metadata.yaml")
        return

    for p in plugins:
        print(f"    [Plugin] {p.name} v{p.version}")
        print(f"        author       : {p.author}")
        print(f"        plugin_id    : {p.plugin_id}")
        print(f"        desc         : {p.desc}")
        print(f"        short_desc   : {p.short_desc}")
        print(f"        display_name : {p.display_name}")
        print(f"        repo         : {p.repo}")
        print(f"        root_dir     : {p.root_dir_name}")
        print(f"        enabled      : {'yes' if p.enabled else 'no'}")
        print(f"        module_path  : {p.module_path}")
        print(f"        config_schema: {'yes' if p.config_schema_path else 'no'}")
        print(f"        data_dir     : {p.data_dir}")

    # ================================================================ #
    # 4. 查看事件处理器
    # ================================================================ #
    banner("[4] Event handlers")
    for p in plugins:
        if not p.enabled:
            print(f"    {p.name}: disabled, skip")
            continue
        try:
            handlers = pm.get_plugin_handlers(p.name)
            print(f"    {p.name}: {len(handlers)} handlers")
            for method_name, event_type in handlers.items():
                print(f"        {method_name} -> {event_type.__name__}")
        except CorePluginNotFoundException as e:
            print(f"    {p.name}: {e}")

    # ================================================================ #
    # 5. 配置管理（_conf_schema.json 默认值）
    # ================================================================ #
    banner("[5] Config management (_conf_schema.json defaults)")
    cfg = pm.config_manager

    for p in plugins:
        print(f"  --- {p.name} ---")

        # 5a. 查看 schema
        if p.config_schema_path:
            schema = PluginConfigManager.load_schema(p.config_schema_path)
            print(f"    Schema keys: {list(schema.keys())}")
            print("    Schema details:")
            for key, defn in schema.items():
                print(f"        {key}: type={defn.get('type')}, default={defn.get('default')}")

            # 5b. 默认值生成
            defaults = cfg.generate_default_config(schema)
            print(f"    Generated defaults: {defaults}")

            # 5c. 合并后配置
            merged = cfg.load_config_with_defaults(p.name, schema)
            print(f"    Merged config: {merged}")

            # 5d. 插件元数据中的 config（原始 dict）
            if p.config:
                print(f"    Metadata config: {p.config}")
        else:
            print("    (no _conf_schema.json)")

        # 5e. 读写测试
        cfg.update_config_value(p.name, "greeting_enabled", False)
        val = cfg.get_config_value(p.name, "greeting_enabled")
        print(f"    update_config_value test: greeting_enabled = {val}")
        # 恢复
        cfg.update_config_value(p.name, "greeting_enabled", True)

    # ================================================================ #
    # 6. 权限管理（Server 自动分配默认值，可逐项修改 + 持久化）
    # ================================================================ #
    banner("[6] Permission management (Server defaults, modifiable, persisted)")
    ppm = pm.permission_manager

    from interfaces.bot import BotPermission

    for p in plugins:
        print(f"  --- {p.name} ---")

        # 6a. 默认权限（Server 自动分配）
        defaults = PluginPermissionManager.default_permissions()
        print(f"    Default permissions (server-assigned): {defaults}")

        # 6b. 加载当前权限（首次自动分配默认值）
        perms = ppm.ensure_permissions(p.name)
        print(f"    Current permissions: {perms}")

        # 6c. 插件实例注入的 permissions
        if p.plugin_instance:
            print(f"    Instance permissions: {p.plugin_instance.permissions}")

        # 6d. 转 BotPermission Flag
        flag = PluginPermissionManager.to_bot_permission(perms)
        print(f"    → BotPermission Flag: {flag} (value={flag.value})")
        assert flag & BotPermission.SEND_LIVESTREAM_MESSAGE
        assert not (flag & BotPermission.EXPOSE_COOKIE)

        # 6e. Round-trip
        d2 = PluginPermissionManager.to_dict(flag)
        print(f"    → Round-trip: {d2}")

        # 6f. 修改权限 — 授予 SEND_GIFT
        ppm.update_permission(p.name, "SEND_GIFT", True)
        val = ppm.load_permissions(p.name)
        print(f"    After granting SEND_GIFT: {val}")
        assert val is not None and val["SEND_GIFT"] is True

        # 6g. 验证持久化 — 从磁盘重新加载
        reloaded = ppm.load_permissions(p.name)
        print(f"    Reloaded from disk: SEND_GIFT = {reloaded['SEND_GIFT'] if reloaded else 'N/A'}")

        # 6h. 恢复
        ppm.update_permission(p.name, "SEND_GIFT", False)
        print("    Restored SEND_GIFT to False")

    # ================================================================ #
    # 6.5. 插件权限拦截验证（current_plugin ContextVar + Bot 校验）
    # ================================================================ #
    banner("[6.5] Permission enforcement (Plugin -> Bot gate)")
    from interfaces.bot import BotPermission as BP
    from interfaces.plugin.plugin import current_plugin
    from core.bot.mis_bot import MissevanBot
    from core.exceptions import CorePermissionException

    # 创建一个拥有全部权限的模拟 Bot
    all_perms = BP(0)
    for p in BP:
        all_perms |= p
    mock_bot = MissevanBot("mock_cookie", permissions=all_perms)
    mock_bot._initialized = True

    # 创建一个权限受限的模拟插件
    restricted_plugin = Plugin(
        permissions={
            "SEND_LIVESTREAM_MESSAGE": True,   # 有此权限
            "SEND_GIFT": False,                 # 无此权限
            "EXPOSE_COOKIE": False,             # 无此权限（敏感）
        },
    )
    restricted_plugin.name = "restricted_demo"

    # 创建一个无 permissions 的插件（向后兼容 — 静默通过）
    legacy_plugin = Plugin(permissions=None)
    legacy_plugin.name = "legacy_demo"

    print("  --- Scenario 1: 插件有权限 → 通过 ---")
    token = current_plugin.set(restricted_plugin)
    try:
        mock_bot._check_plugin_permission(BP.SEND_LIVESTREAM_MESSAGE)
        print("    [PASS] SEND_LIVESTREAM_MESSAGE 已授予，校验通过")
    except CorePermissionException as e:
        print(f"    [FAIL] {e}")
    finally:
        current_plugin.reset(token)

    print("  --- Scenario 2: 插件无权限 → 拒绝 ---")
    token = current_plugin.set(restricted_plugin)
    try:
        mock_bot._check_plugin_permission(BP.SEND_GIFT)
        print("    [FAIL] 应拒绝但通过了")
    except CorePermissionException as e:
        if "restricted_demo" in str(e) and "SEND_GIFT" in str(e):
            print(f"    [PASS] 正确拒绝: {e}")
        else:
            print(f"    [FAIL] 异常内容不符: {e}")
    finally:
        current_plugin.reset(token)

    print("  --- Scenario 3: 插件无 EXPOSE_COOKIE → 拒绝 ---")
    token = current_plugin.set(restricted_plugin)
    try:
        mock_bot._check_plugin_permission(BP.EXPOSE_COOKIE)
        print("    [FAIL] 应拒绝但通过了")
    except CorePermissionException as e:
        print(f"    [PASS] 正确拒绝: {e}")
    finally:
        current_plugin.reset(token)

    print("  --- Scenario 4: 非插件调用 → 静默通过 ---")
    # 确保 current_plugin 为 None（普通调用）
    try:
        mock_bot._check_plugin_permission(BP.SEND_GIFT)
        print("    [PASS] 非插件调用，直接通过（Bot 自身权限检查另有保障）")
    except CorePermissionException as e:
        print(f"    [FAIL] {e}")

    print("  --- Scenario 5: 旧插件无 permissions dict → 向后兼容 ---")
    token = current_plugin.set(legacy_plugin)
    try:
        mock_bot._check_plugin_permission(BP.EXPOSE_COOKIE)
        print("    [PASS] 无 permissions 配置的插件静默通过（向后兼容）")
    except CorePermissionException as e:
        print(f"    [FAIL] {e}")
    finally:
        current_plugin.reset(token)

    print("  --- Scenario 6: 运行时调整权限后立即生效 ---")
    # 先拒绝
    token = current_plugin.set(restricted_plugin)
    try:
        mock_bot._check_plugin_permission(BP.SEND_GIFT)
        print("    [FAIL] 调整前已通过（不应该）")
    except CorePermissionException:
        pass  # expected
    finally:
        current_plugin.reset(token)
    # 修改权限为 True
    restricted_plugin.permissions["SEND_GIFT"] = True  # type: ignore[index]
    # 再次校验 — 应通过
    token = current_plugin.set(restricted_plugin)
    try:
        mock_bot._check_plugin_permission(BP.SEND_GIFT)
        print("    [PASS] SEND_GIFT 改为 True 后校验通过（运行时生效）")
    except CorePermissionException as e:
        print(f"    [FAIL] {e}")
    finally:
        current_plugin.reset(token)
    # 恢复
    restricted_plugin.permissions["SEND_GIFT"] = False  # type: ignore[index]

    print("  --- Scenario 7: 完整发送链路（send_livestream_message 入口）---")
    token = current_plugin.set(restricted_plugin)
    try:
        # 模拟 send_livestream_message 的权限检查顺序：
        # ① Bot 启用检查 → ② Bot 权限检查 → ③ 插件权限检查 ★
        mock_bot._check_enabled()
        mock_bot._check_permission(BP.SEND_LIVESTREAM_MESSAGE)
        mock_bot._check_plugin_permission(BP.SEND_LIVESTREAM_MESSAGE)
        print("    [PASS] 三级检查全部通过：启用→Bot权限→插件权限")
    except CorePermissionException as e:
        print(f"    [FAIL] {e}")
    finally:
        current_plugin.reset(token)
    banner("[7] Plugin data directory (data_dir)")
    for p in plugins:
        print(f"  --- {p.name} ---")
        d = pm.get_plugin_data_dir(p.name)
        print(f"    data_dir path : {d}")
        print(f"    data_dir exists: {'yes' if Path(d).is_dir() else 'no'}")

        # 检查 stats 文件（由插件在 terminate 时写入）
        stats_file = str(Path(d) / "stats.json")
        if Path(stats_file).exists():
            import json
            with open(stats_file, "r") as f:
                stats = json.load(f)
            print(f"    stats.json    : {stats}")
        else:
            print("    stats.json    : (not yet written — created on terminate)")

    # ================================================================ #
    # 8. 查看 README / CHANGELOG
    # ================================================================ #
    banner("[8] README & CHANGELOG")
    for p in plugins:
        readme = pm.get_plugin_readme(p.name)
        if readme:
            first_line = readme.strip().split("\n")[0]
            print(f"    {p.name} README: {first_line}...")
        else:
            print(f"    {p.name} README: (none)")

        changelog = pm.get_plugin_changelog(p.name)
        if changelog:
            first_line = changelog.strip().split("\n")[0]
            print(f"    {p.name} CHANGELOG: {first_line}")
        else:
            print(f"    {p.name} CHANGELOG: (none)")

    # ================================================================ #
    # 9. 禁用 / 启用 / 重载 测试
    # ================================================================ #
    if plugins:
        target = plugins[0].name

        # 9a. 停止 (stop_plugin alias)
        banner("[9a] Stop plugin (disable)")
        pm.stop_plugin(target)
        p = pm.get_plugin(target)
        if p is not None:
            print(f"    {target} enabled: {'yes' if p.enabled else 'no'}")
        print(f"    disabled list: {pm.disabled_plugin_names}")

        # 验证事件处理器已取消注册
        try:
            handlers = pm.get_plugin_handlers(target)
            print(f"    handlers after stop: {len(handlers)} (should be 0 or raise)")
        except CorePluginNotFoundException:
            print("    handlers after stop: (unregistered, as expected)")

        # 9b. 启动 (start_plugin alias)
        banner("[9b] Start plugin (enable)")
        pm.start_plugin(target)
        p = pm.get_plugin(target)
        if p is not None:
            print(f"    {target} enabled: {'yes' if p.enabled else 'no'}")
        handlers = pm.get_plugin_handlers(target)
        print(f"    handlers after start: {len(handlers)}")

        # 9c. 重载
        banner("[9c] Reload plugin")
        async def _reload():
            return await pm.reload_plugin(target)
        new_meta = asyncio.run(_reload())
        print(f"    reloaded: {new_meta.name} v{new_meta.version}")
        print(f"    config preserved: {new_meta.config is not None}")

    # ================================================================ #
    # 10. 失败插件追踪
    # ================================================================ #
    banner("[10] Failed plugin tracking")
    failed = pm.get_failed_plugins()
    print(f"    Failed plugins: {len(failed)}")
    for f in failed:
        print(f"        {f.get('dir_name')}: {f.get('error')}")

    # ================================================================ #
    # 11. 模拟事件触发
    # ================================================================ #
    banner("[11] EventBus handler count")
    total_handlers = event_bus.handler_count
    print(f"    Registered handler entries: {total_handlers}")
    print(f"    Event types with handlers: {event_bus.event_type_count}")

    # ================================================================ #
    # 12. 关闭
    # ================================================================ #
    banner("[12] Shutdown all plugins")
    asyncio.run(pm.shutdown_all())

    # 验证 stats.json 已被写入
    for p in plugins:
        stats_file = str(Path(p.data_dir or "") / "stats.json")
        if Path(stats_file).exists():
            import json
            with open(stats_file, "r") as f:
                stats = json.load(f)
            print(f"    {p.name} stats.json written: {stats}")
        else:
            print(f"    {p.name} stats.json: (not found)")

    # ================================================================ #
    # Summary
    # ================================================================ #
    banner("Demo Complete!")
    print(f"  Plugins loaded    : {len(plugins)}")
    print(f"  Plugins disabled  : {pm.disabled_plugin_names}")
    print(f"  Failed plugins    : {len(failed)}")
    print(f"  EventBus entries  : {total_handlers}")


if __name__ == "__main__":
    main()

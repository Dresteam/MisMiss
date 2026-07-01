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

import os
import sys

# 确保 src/ 在路径中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.events import EventBus
from core.plugin import PluginManager, PluginConfigManager, PluginPermissionManager
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
    project_root = os.path.dirname(os.path.dirname(__file__))
    plugin_dir = os.path.join(project_root, "plugins")
    config_dir = os.path.join(project_root, "data", "config")
    perm_dir = os.path.join(project_root, "data", "permissions")
    data_dir = os.path.join(project_root, "data")

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
            print(f"    Schema details:")
            for key, defn in schema.items():
                print(f"        {key}: type={defn.get('type')}, default={defn.get('default')}")

            # 5b. 默认值生成
            defaults = cfg.generate_default_config(schema)
            print(f"    Generated defaults: {defaults}")

            # 5c. 合并后配置
            merged = cfg.load_config_with_defaults(p.name, schema)
            print(f"    Merged config: {merged}")

            # 5d. 插件实例的 config
            if p.plugin_instance:
                print(f"    Instance config: {p.plugin_instance.config}")
        else:
            print(f"    (no _conf_schema.json)")

        # 5e. 读写测试
        cfg.update_config_value(p.name, "greeting_enabled", False)
        val = cfg.get_config_value(p.name, "greeting_enabled")
        print(f"    update_config_value test: greeting_enabled = {val}")
        # 恢复
        cfg.update_config_value(p.name, "greeting_enabled", True)

    # ================================================================ #
    # 6. 权限管理
    # ================================================================ #
    banner("[6] Permission management (_permission.json)")
    ppm = pm.permission_manager

    for p in plugins:
        print(f"  --- {p.name} ---")
        perm_schema = PluginPermissionManager.load_permission_schema(
            os.path.join(plugin_dir, p.root_dir_name or "")
        )
        if perm_schema:
            print(f"    Permission schema: {perm_schema}")
            defaults = ppm.generate_default_permissions(perm_schema)
            print(f"    Generated defaults: {defaults}")
            merged = ppm.load_permissions_with_defaults(p.name, perm_schema)
            print(f"    Merged permissions: {merged}")
        else:
            print(f"    (no _permission.json)")

        # 读写测试
        ppm.update_permission(p.name, "admin_only", True)
        val = ppm.get_permission(p.name, "admin_only")
        print(f"    update_permission test: admin_only = {val}")
        ppm.update_permission(p.name, "admin_only", False)

    # ================================================================ #
    # 7. 插件数据目录
    # ================================================================ #
    banner("[7] Plugin data directory (data_dir)")
    for p in plugins:
        print(f"  --- {p.name} ---")
        d = pm.get_plugin_data_dir(p.name)
        print(f"    data_dir path : {d}")
        print(f"    data_dir exists: {'yes' if os.path.isdir(d) else 'no'}")

        # 检查 stats 文件（由插件在 terminate 时写入）
        stats_file = os.path.join(d, "stats.json")
        if os.path.exists(stats_file):
            import json
            with open(stats_file, "r") as f:
                stats = json.load(f)
            print(f"    stats.json    : {stats}")
        else:
            print(f"    stats.json    : (not yet written — created on terminate)")

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
        print(f"    {target} enabled: {'yes' if p.enabled else 'no'}")
        print(f"    disabled list: {pm.disabled_plugin_names}")

        # 验证事件处理器已取消注册
        try:
            handlers = pm.get_plugin_handlers(target)
            print(f"    handlers after stop: {len(handlers)} (should be 0 or raise)")
        except CorePluginNotFoundException:
            print(f"    handlers after stop: (unregistered, as expected)")

        # 9b. 启动 (start_plugin alias)
        banner("[9b] Start plugin (enable)")
        pm.start_plugin(target)
        p = pm.get_plugin(target)
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
    total_handlers = sum(len(h) for h in event_bus._handlers.values())
    print(f"    Registered handler entries: {total_handlers}")
    print(f"    Event types with handlers: {len(event_bus._handlers)}")

    # ================================================================ #
    # 12. 关闭
    # ================================================================ #
    banner("[12] Shutdown all plugins")
    asyncio.run(pm.shutdown_all())

    # 验证 stats.json 已被写入
    for p in plugins:
        stats_file = os.path.join(p.data_dir or "", "stats.json")
        if os.path.exists(stats_file):
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

"""插件系统演示。

展示 PluginManager 的核心功能：
1. 扫描并加载插件
2. 查看插件列表和元数据
3. 查看插件事件处理器
4. 查看插件 README / CHANGELOG
5. 禁用和启用插件
6. 卸载插件
7. 配置管理
"""

from __future__ import annotations

import os
import sys

# 确保 src/ 在路径中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.events import EventBus
from core.plugin import PluginManager
from core.exceptions import (
    CorePluginNotFoundException,
)


def main() -> None:
    print("=" * 60)
    print("MisMiss 插件系统演示")
    print("=" * 60)

    # 项目根目录
    project_root = os.path.dirname(os.path.dirname(__file__))
    plugin_dir = os.path.join(project_root, "plugins")
    config_dir = os.path.join(project_root, "data", "config")

    # ================================================================ #
    # 1. 初始化
    # ================================================================ #
    print("\n[1] 初始化 PluginManager ...")
    event_bus = EventBus()
    pm = PluginManager(
        plugin_dir=plugin_dir,
        event_bus=event_bus,
        config_dir=config_dir,
        disabled_plugins=[],
    )
    print(f"    插件目录: {plugin_dir}")
    print(f"    配置目录: {config_dir}")

    # ================================================================ #
    # 2. 加载所有插件
    # ================================================================ #
    print("\n[2] 加载插件 ...")
    import asyncio

    async def _load():
        await pm.load_all()

    asyncio.run(_load())

    # ================================================================ #
    # 3. 查看插件列表
    # ================================================================ #
    print("\n[3] 已加载插件列表:")
    plugins = pm.list_plugins()
    if not plugins:
        print("    (无插件)")
        print("\n⚠ 提示: 请确保 plugins/example_plugin/ 目录存在且包含 main.py 和 metadata.yaml")
        return

    for p in plugins:
        print(f"    📦 {p.name} v{p.version} by {p.author}")
        print(f"       描述: {p.desc}")
        print(f"       目录: {p.root_dir_name}")
        print(f"       启用: {'✅ 是' if p.enabled else '❌ 否'}")
        print(f"       模块: {p.module_path}")

    # ================================================================ #
    # 4. 查看事件处理器
    # ================================================================ #
    print("\n[4] 查看插件事件处理器:")
    for p in plugins:
        if not p.enabled:
            print(f"    {p.name}: 已禁用，跳过")
            continue
        try:
            handlers = pm.get_plugin_handlers(p.name)
            print(f"    {p.name}:")
            for method_name, event_type in handlers.items():
                print(f"        {method_name} -> {event_type.__name__}")
        except CorePluginNotFoundException as e:
            print(f"    {p.name}: {e}")

    # ================================================================ #
    # 5. 查看 README
    # ================================================================ #
    print("\n[5] 查看插件 README:")
    for p in plugins:
        readme = pm.get_plugin_readme(p.name)
        if readme:
            first_line = readme.strip().split("\n")[0]
            print(f"    {p.name}: {first_line}...")
        else:
            print(f"    {p.name}: (无 README.md)")

    # ================================================================ #
    # 6. 查看 CHANGELOG
    # ================================================================ #
    print("\n[6] 查看插件 CHANGELOG:")
    for p in plugins:
        changelog = pm.get_plugin_changelog(p.name)
        if changelog:
            first_line = changelog.strip().split("\n")[0]
            print(f"    {p.name}: {first_line}")
        else:
            print(f"    {p.name}: (无 CHANGELOG.md)")

    # ================================================================ #
    # 7. 禁用插件
    # ================================================================ #
    if plugins:
        target = plugins[0].name
        print(f"\n[7] 禁用插件: {target}")
        pm.disable_plugin(target)
        p = pm.get_plugin(target)
        if p:
            print(f"    启用状态: {'✅ 是' if p.enabled else '❌ 否'}")
            print(f"    禁用列表: {pm.disabled_plugin_names}")

            # 验证事件处理器已被取消注册
            try:
                handlers = pm.get_plugin_handlers(target)
                print(f"    事件处理器: {handlers}（应为空）")
            except CorePluginNotFoundException:
                print(f"    事件处理器: (已取消注册 ✅)")

    # ================================================================ #
    # 8. 启用插件
    # ================================================================ #
    if plugins:
        target = plugins[0].name
        print(f"\n[8] 启用插件: {target}")
        pm.enable_plugin(target)
        p = pm.get_plugin(target)
        if p:
            print(f"    启用状态: {'✅ 是' if p.enabled else '❌ 否'}")
            print(f"    禁用列表: {pm.disabled_plugin_names}")

            # 验证事件处理器已重新注册
            handlers = pm.get_plugin_handlers(target)
            print(f"    事件处理器: {len(handlers)} 个")
            for method_name, event_type in handlers.items():
                print(f"        {method_name} -> {event_type.__name__}")

    # ================================================================ #
    # 9. 配置管理
    # ================================================================ #
    print("\n[9] 配置管理演示:")
    cfg = pm.config_manager

    # 设置配置
    cfg.update_config_value("example_plugin", "greeting_enabled", True)
    cfg.update_config_value("example_plugin", "max_message_length", 500)
    print(f"    已设置配置: greeting_enabled=True, max_message_length=500")

    # 读取配置
    config = cfg.load_config("example_plugin")
    print(f"    读取配置: {config}")

    # 读取单个值
    val = cfg.get_config_value("example_plugin", "greeting_enabled")
    print(f"    读取 greeting_enabled: {val}")
    val = cfg.get_config_value("example_plugin", "nonexistent", default="N/A")
    print(f"    读取 nonexistent (带默认值): {val}")

    # ================================================================ #
    # 10. 自定义事件触发 —— 验证处理器被调用
    # ================================================================ #
    print("\n[10] 模拟事件触发 —— 验证插件处理器:")
    # 使用 EventBus 直接触发一个事件
    # 注意：这里仅演示事件总线机制，实际使用中事件由 WebSocket 路径触发
    print("    事件总线中已注册的处理器数: ", sum(
        len(h) for h in event_bus._handlers.values()
    ))

    # ================================================================ #
    # 总结
    # ================================================================ #
    print("\n" + "=" * 60)
    print("演示完成！")
    print("=" * 60)
    print(f"  已加载插件: {len(plugins)} 个")
    print(f"  已禁用插件: {pm.disabled_plugin_names}")
    print(f"  事件总线处理器组数: {len(event_bus._handlers)}")


if __name__ == "__main__":
    main()

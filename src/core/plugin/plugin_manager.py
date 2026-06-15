"""插件管理器。

负责插件的全生命周期管理：扫描、加载、卸载、启用、禁用、
事件处理器查询和文档获取。
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from core.exceptions import (
    CorePluginConfigException,
    CorePluginLoadException,
    CorePluginMetadataException,
    CorePluginNotFoundException,
)
from core.logging import get_logger
from core.plugin.config_manager import PluginConfigManager
from interfaces.plugin.plugin import Plugin
from interfaces.plugin.plugin_metadata import PluginMetadata

if TYPE_CHECKING:
    from core.events.bus import EventBus

_log = get_logger(__name__)


class PluginManager:
    """插件管理器。

    管理插件的完整生命周期，包括扫描、加载、卸载、启用/禁用、
    事件处理器查询和文档获取。

    插件目录结构::

        plugins/
        └── my_plugin/
            ├── main.py              # 插件类（继承 Plugin）
            ├── metadata.yaml        # 插件元数据（必须）
            ├── _conf_schema.json    # 配置 schema（可选）
            ├── requirements.txt     # 依赖（可选）
            ├── README.md            # 说明文档（可选）
            └── CHANGELOG.md         # 更新日志（可选）

    :param plugin_dir: 插件根目录路径（如 ``"plugins"``）
    :param event_bus: 全局事件总线实例
    :param config_dir: 插件配置存储目录
    :param disabled_plugins: 初始禁用插件名称列表
    """

    def __init__(
        self,
        plugin_dir: str,
        event_bus: "EventBus",
        config_dir: str,
        disabled_plugins: list[str] | None = None,
    ) -> None:
        self._plugin_dir = plugin_dir
        self._event_bus = event_bus
        self._config_dir = config_dir
        self._disabled_plugins: set[str] = set(disabled_plugins or [])

        # plugin_name -> PluginMetadata
        self._plugins: dict[str, PluginMetadata] = {}
        self._config_mgr = PluginConfigManager(config_dir)

    # ------------------------------------------------------------------ #
    # 目录扫描
    # ------------------------------------------------------------------ #

    @staticmethod
    def _find_main_module(plugin_path: str) -> str | None:
        """在插件目录中查找主模块文件。

        优先级：``main.py`` > ``{dir_name}.py``

        :param plugin_path: 插件目录绝对路径
        :return: 主模块文件名（不含 .py），若未找到则返回 ``None``
        """
        dir_name = os.path.basename(plugin_path)

        if os.path.exists(os.path.join(plugin_path, "main.py")):
            return "main"
        if os.path.exists(os.path.join(plugin_path, f"{dir_name}.py")):
            return dir_name
        return None

    def _scan_plugin_dirs(self) -> list[tuple[str, str]]:
        """扫描 ``plugins/`` 目录，发现所有合法插件。

        :return: ``[(dir_name, plugin_dir_path), ...]`` 列表
        """
        if not os.path.exists(self._plugin_dir):
            _log.info("插件目录不存在，跳过扫描: {}", self._plugin_dir)
            return []

        results: list[tuple[str, str]] = []
        for entry in os.listdir(self._plugin_dir):
            full_path = os.path.join(self._plugin_dir, entry)
            if not os.path.isdir(full_path):
                continue
            if entry.startswith("_") or entry.startswith("."):
                continue
            if self._find_main_module(full_path) is None:
                _log.info("插件目录未找到 main.py 或同名 .py，跳过: {}", entry)
                continue
            results.append((entry, full_path))

        return results

    # ------------------------------------------------------------------ #
    # 元数据
    # ------------------------------------------------------------------ #

    @staticmethod
    def _load_metadata(plugin_dir: str) -> PluginMetadata:
        """从 ``metadata.yaml`` 加载插件元数据。

        :param plugin_dir: 插件目录绝对路径
        :return: 插件元数据
        :raises CorePluginMetadataException: 文件不存在或格式错误
        """
        metadata_path = os.path.join(plugin_dir, "metadata.yaml")
        dir_name = os.path.basename(plugin_dir)

        if not os.path.exists(metadata_path):
            raise CorePluginMetadataException(
                dir_name,
                "metadata.yaml 文件不存在",
            )

        try:
            with open(metadata_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise CorePluginMetadataException(
                dir_name,
                f"metadata.yaml 解析失败: {e}",
            )

        if not isinstance(data, dict):
            raise CorePluginMetadataException(
                dir_name,
                "metadata.yaml 格式错误（非映射类型）",
            )

        required_fields = ("name", "author", "desc", "version")
        for field in required_fields:
            if field not in data or not data[field]:
                raise CorePluginMetadataException(
                    dir_name,
                    f"缺少必填字段: {field}",
                )

        return PluginMetadata(
            name=str(data["name"]).strip(),
            author=str(data["author"]).strip(),
            desc=str(data["desc"]).strip(),
            version=str(data["version"]).strip(),
        )

    # ------------------------------------------------------------------ #
    # 加载
    # ------------------------------------------------------------------ #

    async def load_all(self) -> None:
        """扫描并加载 ``plugins/`` 目录下所有插件。

        在 :meth:`MissevanServer.start` 中调用。
        加载失败的插件会被跳过并记录错误日志，不影响其他插件。
        """
        dirs = self._scan_plugin_dirs()
        _log.info("发现 {} 个插件目录", len(dirs))

        for dir_name, plugin_path in dirs:
            try:
                metadata = await self.load_plugin(dir_name, plugin_path)
                if metadata:
                    _log.info("插件加载成功: {}", metadata)
            except CorePluginException as e:
                _log.error("插件加载失败 [{}]: {}", dir_name, e)
            except Exception as e:
                _log.error("插件加载失败 [{}]: {} - {}", dir_name, type(e).__name__, e)

    async def load_plugin(
        self,
        dir_name: str,
        plugin_path: str | None = None,
    ) -> PluginMetadata | None:
        """加载单个插件。

        流程：
        1. 读取 ``metadata.yaml``
        2. 导入模块
        3. 查找 ``Plugin`` 子类并实例化
        4. 调用 ``initialize()``
        5. 注册到事件总线
        6. 按需加载配置

        :param dir_name: 插件目录名
        :param plugin_path: 插件目录绝对路径，若为 ``None`` 则自动拼接
        :return: 插件元数据
        :raises CorePluginMetadataException: 元数据缺失或格式错误
        :raises CorePluginLoadException: 加载失败
        """
        if plugin_path is None:
            plugin_path = os.path.join(self._plugin_dir, dir_name)

        if not os.path.isdir(plugin_path):
            raise CorePluginLoadException(dir_name, "插件目录不存在")

        # 1. 读元数据
        metadata = self._load_metadata(plugin_path)
        metadata.root_dir_name = dir_name

        # 防止重复加载
        if metadata.name in self._plugins:
            _log.warning("插件已加载，跳过: {}", metadata.name)
            return self._plugins[metadata.name]

        # 2. 找主模块
        module_file = self._find_main_module(plugin_path)
        if module_file is None:
            raise CorePluginLoadException(dir_name, "未找到 main.py")

        # 3. 构建导入路径并导入
        import_path = f"plugins.{dir_name}.{module_file}"

        # 确保 plugins/ 在 sys.path 中
        project_root = os.path.dirname(self._plugin_dir) if os.path.isabs(self._plugin_dir) else os.path.abspath(self._plugin_dir)
        if project_root not in sys.path:
            sys.path.insert(0, project_root)

        try:
            module = importlib.import_module(import_path)
        except ImportError as e:
            raise CorePluginLoadException(
                dir_name,
                f"模块导入失败 ({import_path}): {e}",
            ) from e
        except Exception as e:
            raise CorePluginLoadException(
                dir_name,
                f"导入异常: {e}",
            ) from e

        # 4. 查找 Plugin 子类
        plugin_cls = self._find_plugin_class(module, dir_name)

        # 5. 判断是否被禁用
        is_disabled = metadata.name in self._disabled_plugins

        # 6. 实例化插件（禁用时仅创建实例，不注册事件）
        try:
            instance = plugin_cls()
        except Exception as e:
            raise CorePluginLoadException(
                dir_name,
                f"插件实例化失败: {e}",
            ) from e

        metadata.plugin_instance = instance
        metadata.module = module
        metadata.module_path = import_path
        metadata.enabled = not is_disabled

        # 7. 加载配置
        schema_path = os.path.join(plugin_path, "_conf_schema.json")
        if os.path.exists(schema_path):
            metadata.config_schema_path = schema_path

        # 8. 加载 README
        readme_path = os.path.join(plugin_path, "README.md")
        if os.path.exists(readme_path):
            metadata.readme_path = readme_path

        # 9. 初始化并注册
        if not is_disabled:
            try:
                await instance.initialize()
            except Exception as e:
                _log.warning("插件 {} 初始化异常: {}", metadata.name, e)

            self._event_bus.register_new_event(instance)
            _log.info("插件已注册到事件总线: {}", metadata.name)
        else:
            _log.info("插件 {} 当前处于禁用状态，跳过注册", metadata.name)

        # 10. 存入内部字典
        self._plugins[metadata.name] = metadata
        return metadata

    @staticmethod
    def _find_plugin_class(module: object, dir_name: str) -> type[Plugin]:
        """在模块中查找 Plugin 的非抽象子类。

        遍历模块中所有类，找到继承自 :class:`Plugin` 的第一匹配项。

        :param module: Python 模块对象
        :param dir_name: 插件目录名（用于错误信息）
        :return: Plugin 子类
        :raises CorePluginLoadException: 未找到或找到多个
        """
        import inspect

        candidates: list[type[Plugin]] = []
        for attr_name in dir(module):
            obj = getattr(module, attr_name, None)
            if not inspect.isclass(obj):
                continue
            if obj is Plugin:
                continue
            if not issubclass(obj, Plugin):
                continue
            if inspect.isabstract(obj):
                continue
            # 只取本模块定义的类
            if obj.__module__ != module.__name__:
                continue
            candidates.append(obj)

        if len(candidates) == 0:
            raise CorePluginLoadException(
                dir_name,
                "未找到继承自 Plugin 的非抽象类。请在 main.py 中定义一个继承 Plugin 的类。",
            )
        if len(candidates) > 1:
            names = [c.__name__ for c in candidates]
            _log.warning("发现多个 Plugin 子类，使用第一个: {} (全部: {})", names[0], names)

        return candidates[0]

    # ------------------------------------------------------------------ #
    # 卸载
    # ------------------------------------------------------------------ #

    def uninstall_plugin(self, plugin_name: str) -> None:
        """卸载插件。

        调用 :meth:`Plugin.terminate`，从事件总线取消注册，移除插件实例。

        :param plugin_name: 插件名称
        :raises CorePluginNotFoundException: 插件不存在
        """
        metadata = self._get_plugin(plugin_name)
        if metadata.plugin_instance is not None:
            self._unload_plugin_instance(metadata)
        del self._plugins[plugin_name]
        _log.info("插件已卸载: {}", plugin_name)

    # ------------------------------------------------------------------ #
    # 重载
    # ------------------------------------------------------------------ #

    async def reload_plugin(self, plugin_name: str) -> PluginMetadata:
        """重载插件。

        终止 → 取消注册 → 清除模块缓存 → 重新加载。

        :param plugin_name: 插件名称
        :return: 新的插件元数据
        :raises CorePluginNotFoundException: 插件不存在
        """
        metadata = self._get_plugin(plugin_name)
        dir_name = metadata.root_dir_name
        if dir_name is None:
            raise CorePluginLoadException(plugin_name, "root_dir_name 为空")

        # 终止旧实例
        self._unload_plugin_instance(metadata)

        # 清除模块缓存
        self._purge_modules(metadata)

        # 移除旧条目
        del self._plugins[plugin_name]

        # 重新加载
        return await self.load_plugin(dir_name)  # type: ignore[return-value]

    # ------------------------------------------------------------------ #
    # 启用 / 禁用
    # ------------------------------------------------------------------ #

    def enable_plugin(self, plugin_name: str) -> None:
        """启用插件。

        将插件实例注册到事件总线，并更新禁用列表。

        :param plugin_name: 插件名称
        :raises CorePluginNotFoundException: 插件不存在
        """
        metadata = self._get_plugin(plugin_name)
        if metadata.enabled:
            _log.info("插件已处于启用状态: {}", plugin_name)
            return

        if metadata.plugin_instance is None:
            raise CorePluginLoadException(plugin_name, "插件实例为空")

        metadata.enabled = True
        self._disabled_plugins.discard(plugin_name)
        self._event_bus.register_new_event(metadata.plugin_instance)
        _log.info("插件已启用: {}", plugin_name)

    def disable_plugin(self, plugin_name: str) -> None:
        """禁用插件。

        从事件总线取消注册，保留插件实例和文件。

        :param plugin_name: 插件名称
        :raises CorePluginNotFoundException: 插件不存在
        """
        metadata = self._get_plugin(plugin_name)
        if not metadata.enabled:
            _log.info("插件已处于禁用状态: {}", plugin_name)
            return

        self._disabled_plugins.add(plugin_name)
        metadata.enabled = False

        if metadata.plugin_instance is not None:
            self._event_bus.unregister_event(metadata.plugin_instance)
            # 调用终止钩子
            import asyncio

            try:
                loop = asyncio.get_running_loop()
                loop.create_task(metadata.plugin_instance.terminate())
            except RuntimeError:
                # 不在异步上下文中
                pass

        _log.info("插件已禁用: {}", plugin_name)

    # ------------------------------------------------------------------ #
    # 查询
    # ------------------------------------------------------------------ #

    def _get_plugin(self, plugin_name: str) -> PluginMetadata:
        """按名称获取插件元数据（内部使用，不存在时抛异常）。

        :param plugin_name: 插件名称
        :return: 插件元数据
        :raises CorePluginNotFoundException: 插件不存在
        """
        metadata = self._plugins.get(plugin_name)
        if metadata is None:
            raise CorePluginNotFoundException(plugin_name)
        return metadata

    def get_plugin(self, plugin_name: str) -> PluginMetadata | None:
        """按名称获取插件元数据。

        :param plugin_name: 插件名称
        :return: 插件元数据，不存在则返回 ``None``
        """
        return self._plugins.get(plugin_name)

    def list_plugins(self) -> list[PluginMetadata]:
        """列出所有插件的元数据。

        :return: 插件元数据列表（包括已启用和已禁用的）
        """
        return list(self._plugins.values())

    def get_plugin_handlers(self, plugin_name: str) -> dict[str, type]:
        """查看指定插件注册的所有事件处理器。

        遍历事件总线的内部处理器映射，筛选属于该插件实例的条目。

        :param plugin_name: 插件名称
        :return: 方法名到事件类型的映射，如 ``{"on_message": LiveMessageEvent}``
        :raises CorePluginNotFoundException: 插件不存在或未启用
        """
        metadata = self._get_plugin(plugin_name)
        instance = metadata.plugin_instance
        if instance is None or not metadata.enabled:
            raise CorePluginNotFoundException(
                f"{plugin_name}（插件未启用或无实例）"
            )

        result: dict[str, type] = {}
        for event_type, handlers in self._event_bus._handlers.items():
            for _listener, method in handlers:
                if _listener is instance:
                    result[method.__name__] = event_type

        return result

    def get_plugin_readme(self, plugin_name: str) -> str | None:
        """获取插件的 README.md 内容。

        :param plugin_name: 插件名称
        :return: README 文本内容，若不存在则返回 ``None``
        :raises CorePluginNotFoundException: 插件不存在
        """
        metadata = self._get_plugin(plugin_name)
        if metadata.readme_path and os.path.exists(metadata.readme_path):
            try:
                with open(metadata.readme_path, "r", encoding="utf-8") as f:
                    return f.read()
            except OSError as e:
                _log.warning("读取 README 失败 [{}]: {}", plugin_name, e)
        return None

    def get_plugin_changelog(self, plugin_name: str) -> str | None:
        """获取插件的 CHANGELOG.md 内容。

        :param plugin_name: 插件名称
        :return: CHANGELOG 文本内容，若不存在则返回 ``None``
        :raises CorePluginNotFoundException: 插件不存在
        """
        metadata = self._get_plugin(plugin_name)
        if metadata.root_dir_name is None:
            return None

        changelog_path = os.path.join(
            self._plugin_dir, metadata.root_dir_name, "CHANGELOG.md"
        )
        if os.path.exists(changelog_path):
            try:
                with open(changelog_path, "r", encoding="utf-8") as f:
                    return f.read()
            except OSError as e:
                _log.warning("读取 CHANGELOG 失败 [{}]: {}", plugin_name, e)
        return None

    @property
    def disabled_plugin_names(self) -> set[str]:
        """获取当前禁用插件名称集合（只读视图）。"""
        return set(self._disabled_plugins)

    @property
    def config_manager(self) -> PluginConfigManager:
        """获取配置管理器。"""
        return self._config_mgr

    # ------------------------------------------------------------------ #
    # 生命周期
    # ------------------------------------------------------------------ #

    async def shutdown_all(self) -> None:
        """关闭所有插件。

        依次调用每个已启用插件的 :meth:`Plugin.terminate` 方法。
        """
        for metadata in self._plugins.values():
            if metadata.enabled and metadata.plugin_instance is not None:
                try:
                    await metadata.plugin_instance.terminate()
                    _log.debug("插件已终止: {}", metadata.name)
                except Exception as e:
                    _log.warning("插件 {} 终止异常: {}", metadata.name, e)

        _log.info("所有插件已关闭")

    # ------------------------------------------------------------------ #
    # 内部辅助
    # ------------------------------------------------------------------ #

    @staticmethod
    def _unload_plugin_instance(metadata: PluginMetadata) -> None:
        """终止并取消注册一个插件实例。

        :param metadata: 插件元数据
        """
        import asyncio

        instance = metadata.plugin_instance
        if instance is None:
            return

        # 调用 terminate（尝试异步，失败则同步）
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(instance.terminate())
        except RuntimeError:
            pass

        metadata.plugin_instance = None
        metadata.enabled = False

    @staticmethod
    def _purge_modules(metadata: PluginMetadata) -> None:
        """从 ``sys.modules`` 中清除插件相关的所有模块缓存。

        这确保下次加载时能获取到最新的模块代码。

        :param metadata: 插件元数据
        """
        if metadata.module_path is None:
            return

        prefix = metadata.module_path
        # 也清除子模块（如 plugins.my_plugin.utils）
        to_remove = [
            key
            for key in sys.modules
            if key == prefix or key.startswith(prefix + ".")
        ]

        for key in to_remove:
            del sys.modules[key]
            _log.debug("已清除模块缓存: {}", key)

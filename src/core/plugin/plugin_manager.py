"""插件管理器。

负责插件的全生命周期管理：扫描、加载、卸载、启用、禁用、
安装、卸载、重载、事件处理器查询和文档获取。
"""

from __future__ import annotations

import asyncio
import importlib
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

import yaml

from core.exceptions import (
    CorePluginConfigException,
    CorePluginDependencyException,
    CorePluginInstallException,
    CorePluginLoadException,
    CorePluginMetadataException,
    CorePluginNotFoundException,
)
from core.logging import get_logger
from core.plugin.config_manager import PluginConfigManager
from core.plugin.permission_manager import PluginPermissionManager
from interfaces.plugin.plugin import Plugin
from interfaces.plugin.plugin_metadata import PluginMetadata

if TYPE_CHECKING:
    from core.events.bus import EventBus

_log = get_logger(__name__)

# ------------------------------------------------------------------ #
# 常量
# ------------------------------------------------------------------ #

_METADATA_FILENAMES = ("metadata.yaml", "metadata.yml")
"""元数据文件名（按优先级排序）。"""

_CONF_SCHEMA_FILENAME = "_conf_schema.json"
"""配置 schema 文件名。"""


class PluginManager:
    """插件管理器。

    管理插件的完整生命周期，包括扫描、加载、卸载、启用/禁用、
    安装/卸载、重载、事件处理器查询和文档获取。

    插件目录结构::

        plugins/
        └── my_plugin/
            ├── main.py              # 插件类（继承 Plugin）
            ├── metadata.yaml        # 插件元数据（必须）
            ├── _conf_schema.json    # 配置 schema（可选）
            ├── _permission.json     # 权限 schema（可选）
            ├── requirements.txt     # 依赖（可选）
            ├── README.md            # 说明文档（可选）
            └── CHANGELOG.md         # 更新日志（可选）

    :param plugin_dir: 插件根目录路径（如 ``"plugins"``）
    :param event_bus: 全局事件总线实例
    :param config_dir: 插件配置存储目录
    :param permission_dir: 插件权限配置存储目录
    :param disabled_plugins: 初始禁用插件名称列表
    """

    def __init__(
        self,
        plugin_dir: str,
        event_bus: "EventBus",
        config_dir: str,
        permission_dir: str | None = None,
        plugin_data_dir: str | None = None,
        disabled_plugins: list[str] | None = None,
        on_state_changed: Callable[[], None] | None = None,
    ) -> None:
        self._plugin_dir = plugin_dir
        self._event_bus = event_bus
        self._config_dir = config_dir
        self._disabled_plugins: set[str] = set(disabled_plugins or [])
        self._on_state_changed = on_state_changed

        # 权限目录默认与 config 同级
        if permission_dir is None:
            permission_dir = os.path.join(
                os.path.dirname(config_dir), "permissions"
            )
        self._permission_dir = permission_dir

        # 插件数据目录默认在 data/ 下
        if plugin_data_dir is None:
            plugin_data_dir = os.path.join(
                os.path.dirname(os.path.dirname(config_dir)), ""
            )
        self._plugin_data_dir = plugin_data_dir

        # plugin_name -> PluginMetadata
        self._plugins: dict[str, PluginMetadata] = {}
        self._config_mgr = PluginConfigManager(config_dir)
        self._permission_mgr = PluginPermissionManager(permission_dir)

        # 失败插件追踪: dir_name -> error_info
        self._failed_plugins: dict[str, dict[str, Any]] = {}

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
                _log.info(
                    "插件目录未找到 main.py 或同名 .py，跳过: {}", entry
                )
                continue
            results.append((entry, full_path))

        return results

    # ------------------------------------------------------------------ #
    # 元数据
    # ------------------------------------------------------------------ #

    @staticmethod
    def _find_metadata_file(plugin_dir: str) -> str | None:
        """在插件目录中查找元数据文件。

        按 ``metadata.yaml`` > ``metadata.yml`` 优先级搜索。

        :param plugin_dir: 插件目录绝对路径
        :return: 元数据文件路径，不存在则返回 ``None``
        """
        for fname in _METADATA_FILENAMES:
            path = os.path.join(plugin_dir, fname)
            if os.path.exists(path):
                return path
        return None

    @staticmethod
    def _load_metadata(plugin_dir: str) -> PluginMetadata:
        """从 ``metadata.yaml``（或 ``metadata.yml``）加载插件元数据。

        :param plugin_dir: 插件目录绝对路径
        :return: 插件元数据
        :raises CorePluginMetadataException: 文件不存在或格式错误
        """
        metadata_path = PluginManager._find_metadata_file(plugin_dir)
        dir_name = os.path.basename(plugin_dir)

        if metadata_path is None:
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
                f"metadata 解析失败: {e}",
            )

        if not isinstance(data, dict):
            raise CorePluginMetadataException(
                dir_name,
                "metadata 格式错误（非映射类型）",
            )

        required_fields = ("name", "author", "desc", "version")
        for field in required_fields:
            if field not in data or not data[field]:
                raise CorePluginMetadataException(
                    dir_name,
                    f"缺少必填字段: {field}",
                )

        # 兼容 desc/description 两种写法
        desc = str(data.get("desc") or data.get("description") or "").strip()

        return PluginMetadata(
            name=str(data["name"]).strip(),
            author=str(data["author"]).strip(),
            desc=desc,
            version=str(data["version"]).strip(),
            # 可选字段
            short_desc=str(data.get("short_desc", "")).strip() or None,
            repo=str(data.get("repo", "")).strip() or None,
            display_name=str(data.get("display_name", "")).strip() or None,
        )

    # ------------------------------------------------------------------ #
    # 依赖处理
    # ------------------------------------------------------------------ #

    @staticmethod
    def _find_requirements(plugin_dir: str) -> str | None:
        """在插件目录中查找 ``requirements.txt``。

        :param plugin_dir: 插件目录绝对路径
        :return: 文件路径，不存在则返回 ``None``
        """
        path = os.path.join(plugin_dir, "requirements.txt")
        if os.path.exists(path):
            return path
        return None

    @staticmethod
    def _install_requirements(
        requirements_path: str,
        plugin_name: str,
    ) -> None:
        """安装 ``requirements.txt`` 中缺失的依赖。

        对每个包检查是否已安装，仅安装缺失的包。

        :param requirements_path: requirements.txt 绝对路径
        :param plugin_name: 插件名称（用于日志和异常信息）
        :raises CorePluginDependencyException: 安装失败
        """
        try:
            with open(requirements_path, "r", encoding="utf-8") as f:
                lines = f.read().strip()
        except OSError as e:
            _log.warning(
                "无法读取 requirements.txt [{}]: {}", plugin_name, e
            )
            return

        if not lines:
            return

        packages = [
            line.strip()
            for line in lines.split("\n")
            if line.strip() and not line.strip().startswith("#")
        ]
        if not packages:
            return

        _log.info(
            "正在为插件 [{}] 安装依赖: {} 个包", plugin_name, len(packages)
        )

        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "--quiet",
                    *packages,
                ],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode != 0:
                stderr = result.stderr.strip()
                _log.warning(
                    "插件 [{}] 部分依赖安装可能失败: {}",
                    plugin_name,
                    stderr[:500],
                )
            else:
                _log.info("插件 [{}] 依赖安装完成", plugin_name)
        except subprocess.TimeoutExpired:
            raise CorePluginDependencyException(
                plugin_name, "依赖安装超时（超过 120 秒）"
            )
        except FileNotFoundError:
            raise CorePluginDependencyException(
                plugin_name, "未找到 pip，请确保 Python 环境中已安装 pip"
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
            except CorePluginLoadException as e:
                _log.error("插件加载失败 [{}]: {}", dir_name, e)
            except CorePluginMetadataException as e:
                _log.error("插件元数据错误 [{}]: {}", dir_name, e)
            except CorePluginDependencyException as e:
                _log.error("插件依赖错误 [{}]: {}", dir_name, e)
            except Exception as e:
                _log.error(
                    "插件加载失败 [{}]: {} - {}", dir_name, type(e).__name__, e
                )

    async def load_plugin(
        self,
        dir_name: str,
        plugin_path: str | None = None,
    ) -> PluginMetadata | None:
        """加载单个插件。

        流程：
        1. 读取 ``metadata.yaml``
        2. 安装 ``requirements.txt`` 依赖
        3. 导入模块
        4. 加载 ``_conf_schema.json`` → 生成配置（含默认值）
        5. 加载 ``_permission.json`` → 生成权限配置（含默认值）
        6. 查找 ``Plugin`` 子类并实例化（传入 config）
        7. 注入元数据属性（name / author / plugin_id）
        8. 调用 ``initialize()``
        9. 注册到事件总线

        :param dir_name: 插件目录名
        :param plugin_path: 插件目录绝对路径，若为 ``None`` 则自动拼接
        :return: 插件元数据
        :raises CorePluginMetadataException: 元数据缺失或格式错误
        :raises CorePluginLoadException: 加载失败
        :raises CorePluginDependencyException: 依赖安装失败
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

        # 2. 安装依赖
        requirements_path = self._find_requirements(plugin_path)
        if requirements_path:
            metadata.requirements_path = requirements_path
            self._install_requirements(requirements_path, metadata.name)

        # 3. 找主模块
        module_file = self._find_main_module(plugin_path)
        if module_file is None:
            raise CorePluginLoadException(dir_name, "未找到 main.py")

        # 4. 构建导入路径并导入
        import_path = f"plugins.{dir_name}.{module_file}"

        # 确保 plugins/ 在 sys.path 中
        project_root = (
            os.path.dirname(self._plugin_dir)
            if os.path.isabs(self._plugin_dir)
            else os.path.abspath(self._plugin_dir)
        )
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

        # 5. 查找 Plugin 子类
        plugin_cls = self._find_plugin_class(module, dir_name)

        # 6. 加载配置（_conf_schema.json）
        plugin_config: dict = {}
        schema_path = os.path.join(plugin_path, _CONF_SCHEMA_FILENAME)
        if os.path.exists(schema_path):
            metadata.config_schema_path = schema_path
            try:
                schema = PluginConfigManager.load_schema(schema_path)
                if schema:
                    plugin_config = self._config_mgr.load_config_with_defaults(
                        metadata.name,
                        schema,
                    )
                    _log.debug(
                        "插件 [{}] 配置已加载 ({} 项)",
                        metadata.name,
                        len(plugin_config),
                    )
            except CorePluginConfigException as e:
                _log.warning("插件 [{}] 配置加载失败: {}", metadata.name, e)

        # 7. 加载权限（Server 自动分配默认权限，对标 Bot 默认值）
        plugin_permissions: dict[str, bool] = (
            self._permission_mgr.ensure_permissions(metadata.name)
        )
        _log.debug(
            "插件 [{}] 权限已加载 ({} 项): {}",
            metadata.name,
            len(plugin_permissions),
            [k for k, v in plugin_permissions.items() if v],
        )

        # 8. 判断是否被禁用
        is_disabled = metadata.name in self._disabled_plugins

        # 9. 实例化插件（传入 config 和 permissions）
        try:
            kwargs: dict = {}
            if plugin_config is not None:
                kwargs["config"] = plugin_config
            if plugin_permissions is not None:
                kwargs["permissions"] = plugin_permissions
            instance = plugin_cls(**kwargs)
        except Exception as e:
            raise CorePluginLoadException(
                dir_name,
                f"插件实例化失败: {e}",
            ) from e

        # 注入元数据属性
        instance.name = metadata.name
        instance.author = metadata.author
        instance.plugin_id = metadata.plugin_id

        # 创建并注入数据目录
        data_dir = self.get_plugin_data_dir(metadata.name)
        instance.data_dir = data_dir
        metadata.data_dir = data_dir

        metadata.plugin_instance = instance
        metadata.module = module
        metadata.module_path = import_path
        metadata.config = plugin_config
        metadata.permissions = plugin_permissions
        metadata.enabled = not is_disabled

        # 10. 加载 README
        readme_path = os.path.join(plugin_path, "README.md")
        if os.path.exists(readme_path):
            metadata.readme_path = readme_path

        # 11. 初始化并注册
        if not is_disabled:
            try:
                await instance.initialize()
            except Exception as e:
                _log.warning("插件 {} 初始化异常: {}", metadata.name, e)

            self._event_bus.register_new_event(instance)
            _log.info("插件已注册到事件总线: {}", metadata.name)
        else:
            _log.info(
                "插件 {} 当前处于禁用状态，跳过注册", metadata.name
            )

        # 12. 存入内部字典
        self._plugins[metadata.name] = metadata

        # 从失败列表移除（如果有重试）
        self._failed_plugins.pop(dir_name, None)

        self._notify_state_changed()
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
            obj = obj
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
            _log.warning(
                "发现多个 Plugin 子类，使用第一个: {} (全部: {})",
                names[0],
                names,
            )

        return candidates[0]

    # ------------------------------------------------------------------ #
    # 卸载
    # ------------------------------------------------------------------ #

    def uninstall_plugin(
        self,
        plugin_name: str,
        delete_config: bool = False,
        delete_data: bool = False,
    ) -> None:
        """卸载插件。

        终止插件 → 取消事件注册 → 移除插件实例 → 清除模块缓存。
        根据参数可选删除配置文件和插件目录。

        :param plugin_name: 插件名称
        :param delete_config: 是否删除插件配置文件
        :param delete_data: 是否删除插件目录（``plugins/{root_dir_name}/``）
        :raises CorePluginNotFoundException: 插件不存在
        """
        metadata = self._get_plugin(plugin_name)
        root_dir = metadata.root_dir_name

        # 终止并取消注册
        if metadata.plugin_instance is not None:
            self._unload_plugin_instance(metadata)

        # 清理模块缓存
        self._purge_modules(metadata)

        # 删除配置文件
        if delete_config:
            try:
                self._config_mgr.delete_config_file(plugin_name)
            except Exception as e:
                _log.warning("删除配置文件失败 [{}]: {}", plugin_name, e)
            try:
                self._permission_mgr.delete_permissions(plugin_name)
            except Exception as e:
                _log.warning("删除权限配置失败 [{}]: {}", plugin_name, e)

        # 删除插件数据目录
        if delete_data:
            try:
                self.delete_plugin_data_dir(plugin_name)
            except Exception as e:
                _log.warning("删除数据目录失败 [{}]: {}", plugin_name, e)

        # 删除插件目录
        if delete_data and root_dir:
            plugin_path = os.path.join(self._plugin_dir, root_dir)
            if os.path.isdir(plugin_path):
                try:
                    shutil.rmtree(plugin_path)
                    _log.info("插件目录已删除: {}", plugin_path)
                except OSError as e:
                    _log.error("删除插件目录失败 [{}]: {}", plugin_name, e)

        # 从内部字典移除
        del self._plugins[plugin_name]
        self._disabled_plugins.discard(plugin_name)
        self._failed_plugins.pop(root_dir, None)  # type: ignore[arg-type]
        self._notify_state_changed()
        _log.info("插件已卸载: {}", plugin_name)

    # ------------------------------------------------------------------ #
    # 重载
    # ------------------------------------------------------------------ #

    async def reload_plugin(self, plugin_name: str) -> PluginMetadata:
        """重载插件。

        终止 → 取消注册 → 清除模块缓存 → 重新检测依赖 → 重新加载。

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

        # 重新加载（load_plugin 会重新检测 requirements.txt 变更）
        return await self.load_plugin(dir_name)  # type: ignore[return-value]

    # ------------------------------------------------------------------ #
    # 启用 / 禁用（启动 / 停止）
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
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(metadata.plugin_instance.terminate())
            except RuntimeError:
                # 不在异步上下文中
                pass

        _log.info("插件已禁用: {}", plugin_name)

    # 别名
    start_plugin = enable_plugin
    stop_plugin = disable_plugin

    # ------------------------------------------------------------------ #
    # 安装（从 URL / 本地路径）
    # ------------------------------------------------------------------ #

    async def install_plugin(
        self,
        url: str | None = None,
        local_path: str | None = None,
    ) -> PluginMetadata:
        """安装插件。

        支持从远程 URL 下载或从本地路径复制。

        :param url: 插件 zip 包的远程 URL（GitHub release 等）
        :param local_path: 本地 zip 文件或目录路径
        :return: 安装后的插件元数据
        :raises CorePluginInstallException: 安装失败
        """
        if url is None and local_path is None:
            raise CorePluginInstallException(
                "", "必须提供 url 或 local_path 参数"
            )

        # 1. 获取 zip 文件路径
        if local_path:
            zip_path = local_path
            need_cleanup = False
        else:
            zip_path = await self._download_plugin(url)  # type: ignore[arg-type]
            need_cleanup = True

        try:
            # 2. 解压到临时目录，先检查元数据获取真实 name
            with tempfile.TemporaryDirectory() as tmpdir:
                if os.path.isdir(zip_path):
                    # 本地目录：直接复制
                    dir_name = os.path.basename(zip_path.rstrip("/\\"))
                    dest = os.path.join(self._plugin_dir, dir_name)
                    if os.path.exists(dest):
                        shutil.rmtree(dest)
                    shutil.copytree(zip_path, dest)
                elif zip_path.endswith((".zip", ".tar.gz", ".tgz")):
                    self._extract_archive(zip_path, tmpdir)
                    # 查找解压后的根目录（可能有嵌套）
                    extracted_dirs = [
                        d
                        for d in os.listdir(tmpdir)
                        if os.path.isdir(os.path.join(tmpdir, d))
                        and not d.startswith("_")
                        and not d.startswith(".")
                    ]
                    if not extracted_dirs:
                        raise CorePluginInstallException(
                            "", "压缩包中未找到插件目录"
                        )
                    # 取第一个非隐藏目录
                    src_dir = os.path.join(tmpdir, extracted_dirs[0])
                    dir_name = extracted_dirs[0]

                    # 读取 metadata 获取正式名称
                    canonical_name = self._read_plugin_name_from_dir(src_dir)
                    if canonical_name:
                        dir_name = canonical_name

                    dest = os.path.join(self._plugin_dir, dir_name)
                    if os.path.exists(dest):
                        shutil.rmtree(dest)
                    shutil.copytree(src_dir, dest)
                else:
                    raise CorePluginInstallException(
                        "", f"不支持的文件格式: {zip_path}"
                    )

            # 3. 安装依赖
            req_path = self._find_requirements(dest)
            if req_path:
                self._install_requirements(req_path, dir_name)

            # 4. 加载插件
            _log.info("插件文件已就绪，开始加载: {}", dir_name)
            metadata = await self.load_plugin(dir_name)
            if metadata is None:
                raise CorePluginInstallException(
                    dir_name, "插件文件已解压但加载失败"
                )

            _log.info("插件安装成功: {}", metadata)
            return metadata

        finally:
            if need_cleanup and os.path.exists(zip_path):
                try:
                    os.remove(zip_path)
                except OSError:
                    pass

    @staticmethod
    async def _download_plugin(url: str) -> str:
        """下载插件 zip 包到临时文件。

        :param url: 下载 URL
        :return: 临时文件路径
        :raises CorePluginInstallException: 下载失败
        """
        _log.info("正在下载插件: {}", url)
        try:
            # 在 executor 中执行同步下载
            loop = asyncio.get_running_loop()

            def _download():
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": "MisMiss-PluginManager/1.0"},
                )
                with urllib.request.urlopen(req, timeout=60) as resp:
                    return resp.read()

            data = await loop.run_in_executor(None, _download)  # type: ignore[arg-type]

            suffix = ".zip"
            if url.endswith(".tar.gz") or url.endswith(".tgz"):
                suffix = ".tar.gz"

            tmp = tempfile.NamedTemporaryFile(  # type: ignore[call-arg]
                delete=False, suffix=suffix
            )
            tmp.write(data)
            tmp.close()
            _log.info("插件下载完成: {} bytes", len(data))
            return tmp.name

        except urllib.error.URLError as e:
            raise CorePluginInstallException("", f"下载失败: {e}")
        except Exception as e:
            raise CorePluginInstallException("", f"下载异常: {e}")

    @staticmethod
    def _extract_archive(archive_path: str, dest_dir: str) -> None:
        """解压 zip 或 tar.gz 到目标目录。

        :param archive_path: 压缩包路径
        :param dest_dir: 目标目录
        :raises CorePluginInstallException: 解压失败
        """
        try:
            if archive_path.endswith((".tar.gz", ".tgz")):
                import tarfile

                with tarfile.open(archive_path, "r:gz") as tar:
                    tar.extractall(dest_dir)
            else:
                with zipfile.ZipFile(archive_path, "r") as zf:
                    zf.extractall(dest_dir)
        except Exception as e:
            raise CorePluginInstallException("", f"解压失败: {e}")

    @staticmethod
    def _read_plugin_name_from_dir(plugin_dir: str) -> str | None:
        """从插件目录读取 metadata 中的正式名称。

        :param plugin_dir: 插件目录绝对路径
        :return: 插件名称，读取失败则返回 ``None``
        """
        try:
            metadata = PluginManager._load_metadata(plugin_dir)
            return metadata.name
        except CorePluginMetadataException:
            return None

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

        result: dict[str, type] = self._event_bus.get_listener_handlers(instance)

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

    # ------------------------------------------------------------------ #
    # 失败插件追踪
    # ------------------------------------------------------------------ #

    def get_failed_plugins(self) -> list[dict[str, Any]]:
        """获取加载失败的插件信息列表。

        :return: 失败插件信息列表，每项包含 ``dir_name``、``error`` 等字段
        """
        return list(self._failed_plugins.values())

    async def retry_failed_plugin(self, dir_name: str) -> PluginMetadata:
        """重试加载之前失败的插件。

        :param dir_name: 插件目录名
        :return: 插件元数据
        :raises CorePluginLoadException: 重试仍然失败
        """
        if dir_name not in self._failed_plugins:
            raise CorePluginNotFoundException(dir_name)

        _log.info("正在重试加载插件: {}", dir_name)
        return await self.load_plugin(dir_name)  # type: ignore[return-value]

    def _record_failed_plugin(
        self,
        dir_name: str,
        error: str,
        metadata: PluginMetadata | None = None,
    ) -> None:
        """记录一个加载失败的插件。

        :param dir_name: 插件目录名
        :param error: 错误描述
        :param metadata: 部分元数据（如有）
        """
        record: dict[str, Any] = {
            "dir_name": dir_name,
            "error": error,
        }
        if metadata is not None:
            record["name"] = metadata.name
            record["author"] = metadata.author
            record["version"] = metadata.version
        self._failed_plugins[dir_name] = record

    @property
    def disabled_plugin_names(self) -> set[str]:
        """获取当前禁用插件名称集合（只读视图）。"""
        return set(self._disabled_plugins)

    @property
    def config_manager(self) -> PluginConfigManager:
        """获取配置管理器。"""
        return self._config_mgr

    @property
    def permission_manager(self) -> PluginPermissionManager:
        """获取权限配置管理器。"""
        return self._permission_mgr

    # ------------------------------------------------------------------ #
    # 插件数据目录
    # ------------------------------------------------------------------ #

    def get_plugin_data_dir(self, plugin_name: str) -> str:
        """获取（并创建）插件的专属数据目录。

        目录路径为 ``{plugin_data_dir}/{plugin_name}/``，
        若不存在则自动创建。

        插件可将数据库、缓存等自定义文件存储在此目录下。

        :param plugin_name: 插件名称
        :return: 数据目录绝对路径
        """
        safe_name = plugin_name.replace("/", "_").replace("\\", "_")
        data_dir = os.path.join(self._plugin_data_dir, safe_name)
        Path(data_dir).mkdir(parents=True, exist_ok=True)
        return data_dir

    def delete_plugin_data_dir(self, plugin_name: str) -> None:
        """删除插件的专属数据目录。

        :param plugin_name: 插件名称
        """
        safe_name = plugin_name.replace("/", "_").replace("\\", "_")
        data_dir = os.path.join(self._plugin_data_dir, safe_name)
        if os.path.isdir(data_dir):
            shutil.rmtree(data_dir)
            _log.info("插件数据目录已删除: {}", data_dir)

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
                    _log.warning(
                        "插件 {} 终止异常: {}", metadata.name, e
                    )

        _log.info("所有插件已关闭")

    # ------------------------------------------------------------------ #
    # 内部辅助
    # ------------------------------------------------------------------ #

    def _notify_state_changed(self) -> None:
        """通知外部（如 Server）插件状态已变更，需要持久化。"""
        if self._on_state_changed is not None:
            self._on_state_changed()

    def _unload_plugin_instance(self, metadata: PluginMetadata) -> None:
        """终止并取消注册一个插件实例。

        1. 从事件总线取消注册
        2. 调用插件的 ``terminate()`` 钩子
        3. 清空实例引用

        :param metadata: 插件元数据
        """
        instance = metadata.plugin_instance
        if instance is None:
            return

        # 从事件总线取消注册
        self._event_bus.unregister_event(instance)

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

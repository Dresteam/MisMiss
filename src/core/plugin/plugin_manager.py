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
from core.plugin.data_manager import PluginDataManager
from core.plugin.permission_manager import PluginPermissionManager
from interfaces.plugin.miss_config import MissConfig
from interfaces.plugin.plugin import Plugin
from interfaces.plugin.plugin_metadata import PluginMetadata

if TYPE_CHECKING:
    from core.events.bus import EventBus
    from core.command.router import CommandRouter

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
        command_router: "CommandRouter | None" = None,
        pip_mirror: str | None = None,
    ) -> None:
        self._plugin_dir = plugin_dir
        self._event_bus = event_bus
        self._config_dir = config_dir
        self._disabled_plugins: set[str] = set(disabled_plugins or [])
        self._on_state_changed = on_state_changed
        self._command_router = command_router
        self._pip_mirror = pip_mirror

        if permission_dir is None:
            permission_dir = os.path.join(os.path.dirname(config_dir), "permissions")
        self._permission_dir = permission_dir
        if plugin_data_dir is None:
            plugin_data_dir = os.path.join(os.path.dirname(config_dir), "plugins")
        self._plugin_data_dir = plugin_data_dir

        self._plugins: dict[str, PluginMetadata] = {}
        self._config_mgr = PluginConfigManager(config_dir)
        self._permission_mgr = PluginPermissionManager(permission_dir)
        self._failed_plugins: dict[str, dict[str, Any]] = {}
        self._app = None  # FastAPI app 引用
        self._server = None  # MissevanServer 引用，供插件获取直播间列表等
        self._server = None  # MissevanServer 引用

    def set_server(self, server) -> None:
        """注入 MissevanServer 引用，供插件查询直播间列表等。"""
        self._server = server

    def set_app(self, app) -> None:
        """设置 FastAPI app 引用并注册所有插件的 UI 路由。

        若插件尚未实例化（如 Bot 未启用时仅加载了元数据），
        会通过 :meth:`_ensure_plugin_loaded` 创建轻量实例以注册路由。
        已存在的实例（已初始化或暂停恢复）不会被重新创建。
        """
        self._app = app
        for name, meta in list(self._plugins.items()):
            if not meta.ui_schema_path or not os.path.exists(meta.ui_schema_path):
                _log.debug("跳过无 UI schema 的插件: {}", name)
                continue
            _log.info("注册 UI 路由: {} (inst={}, initialized={})",
                      name, meta.plugin_instance is not None, meta.initialized)
            if meta.plugin_instance is None:
                self._ensure_plugin_loaded(meta)
            if meta.plugin_instance is not None and hasattr(meta.plugin_instance, 'register_routes'):
                # 仅当路由尚未注册时才注册（避免重复注册同一前缀）
                self._register_routes_if_needed(meta)
                _log.info("插件已注册 UI 路由: {}", name)
            else:
                _log.warning("插件实例不可用或缺少 register_routes: {}", name)

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

    def _install_requirements(
        self,
        requirements_path: str,
        plugin_name: str,
    ) -> None:
        """安装 ``requirements.txt`` 中缺失的依赖。

        逐个检查包是否已安装，仅对缺失的包使用镜像源安装。

        :param requirements_path: requirements.txt 绝对路径
        :param plugin_name: 插件名称（用于日志和异常信息）
        :raises CorePluginDependencyException: 安装失败
        """
        mirror = self._pip_mirror or "https://pypi.tuna.tsinghua.edu.cn/simple"

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

        # 逐个检查，分离已安装和缺失的包
        missing: list[str] = []
        for pkg_spec in packages:
            pkg_name = PluginManager._parse_package_name(pkg_spec)
            if PluginManager._is_package_installed(pkg_name):
                _log.debug("插件 [{}] 依赖已安装，跳过: {}", plugin_name, pkg_name)
            else:
                missing.append(pkg_spec)
                _log.debug("插件 [{}] 依赖缺失，待安装: {}", plugin_name, pkg_name)

        if not missing:
            _log.info("插件 [{}] 所有 {} 个依赖已安装", plugin_name, len(packages))
            return

        _log.info(
            "插件 [{}] 依赖: {} 个中 {} 个缺失，正在安装 ...",
            plugin_name, len(packages), len(missing),
        )

        try:
            # PyInstaller exe 中不能 import pip（会导致 distlib 错误），
            # 统一用 subprocess 调用系统 pip
            import subprocess
            cmd = [sys.executable, "-m", "pip", "install", "--no-cache-dir", "-i", mirror, *missing]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                err = (result.stderr + result.stdout).strip()
                _log.error("插件 [{}] 依赖安装失败 (exit {}): {}",
                           plugin_name, result.returncode, err[:500])
                raise CorePluginDependencyException(
                    plugin_name,
                    f"依赖安装失败 (exit {result.returncode}): {err[:300]}",
                )
            _log.info("插件 [{}] 依赖安装完成 ({}/{} 个)", plugin_name, len(missing), len(packages))
            # 刷新 import 缓存，确保 find_spec 能看到新安装的包
            import importlib
            importlib.invalidate_caches()
            # 验证：逐个确认包是否真正可导入
            still_missing = [p for p in missing if not PluginManager._is_package_installed(
                PluginManager._parse_package_name(p))]
            if still_missing:
                _log.error("插件 [{}] pip 成功但包仍不可见: {} (sys.prefix={})",
                           plugin_name, still_missing, sys.prefix)
        except CorePluginDependencyException:
            raise
        except Exception as e:
            raise CorePluginDependencyException(
                plugin_name, f"依赖安装失败: {e}"
            )

    @staticmethod
    def _parse_package_name(pkg_spec: str) -> str:
        """从 pip 包规格中提取包名（去除版本约束和 extras）。

        :param pkg_spec: 如 ``"pypinyin>=0.50"`` 或 ``"pkg[extra]==1.0"``
        :return: 纯包名，如 ``"pypinyin"``
        """
        name = pkg_spec.strip()
        # 去除 extras: pkg[extra] → pkg
        if "[" in name:
            name = name.split("[")[0]
        # 去除版本约束: pkg>=1.0 → pkg
        for sep in ("==", ">=", "<=", "!=", "~=", ">", "<"):
            if sep in name:
                name = name.split(sep)[0]
                break
        return name.strip().lower().replace("-", "_")

    @staticmethod
    def _is_package_installed(pkg_name: str) -> bool:
        """检查指定的 Python 包是否已安装。

        优先使用 importlib.util.find_spec 检查（无副作用），
        失败时回退到 importlib.metadata（pip 注册名可能与 import 名不同）。

        :param pkg_name: 规范化的包名（小写、下划线）
        :return: 已安装返回 ``True``
        """
        import importlib.util
        # 1. 检查模块是否可被发现（无副作用，最快）
        spec = importlib.util.find_spec(pkg_name)
        if spec is not None:
            return True
        # 2. 检查包名与 import 名不同的情况（如 pkg-name → pkg_name）
        dash_name = pkg_name.replace("_", "-")
        if dash_name != pkg_name:
            spec = importlib.util.find_spec(dash_name)
            if spec is not None:
                return True
        # 3. 回退：通过 pip 元数据检查
        try:
            import importlib.metadata
            importlib.metadata.distribution(pkg_name)
            return True
        except Exception:
            pass
        try:
            importlib.metadata.distribution(dash_name)
            return True
        except Exception:
            pass
        return False

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

        # 2. 检查是否存在 _conf_schema.json / _ui_schema.json（仅记录路径）
        schema_path = os.path.join(plugin_path, _CONF_SCHEMA_FILENAME)
        if os.path.exists(schema_path):
            metadata.config_schema_path = schema_path
        ui_schema_path = os.path.join(plugin_path, "_ui_schema.json")
        if os.path.exists(ui_schema_path):
            metadata.ui_schema_path = ui_schema_path

        # 3. 记录 README 路径
        readme_path = os.path.join(plugin_path, "README.md")
        if os.path.exists(readme_path):
            metadata.readme_path = readme_path

        # 4. 记录路径信息用于后续完整加载
        metadata.module_path = None  # 尚未导入
        metadata.plugin_instance = None
        metadata.enabled = False  # 新插件默认禁用

        # 5. 存入内部字典（仅元数据，不加载代码）
        self._plugins[metadata.name] = metadata
        self._failed_plugins.pop(dir_name, None)
        self._notify_state_changed()
        _log.info("插件已发现（禁用状态）: {}", metadata)
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

        # 保存启停标记
        was_enabled = metadata.enabled

        # 移除旧条目
        del self._plugins[plugin_name]

        # 重新加载（load_plugin 会重新检测 requirements.txt 变更）
        new_meta = await self.load_plugin(dir_name)
        new_meta.enabled = was_enabled  # 恢复原标记
        return new_meta  # type: ignore[return-value]

    # ------------------------------------------------------------------ #
    # 启用 / 禁用（启动 / 停止）
    # ------------------------------------------------------------------ #

    async def _activate_plugin(self, metadata: PluginMetadata) -> None:
        """完整加载一个尚未激活的插件（导入、实例化、初始化、注册）。

        若实例已存在（如 :meth:`set_app` 通过 :meth:`_ensure_plugin_loaded`
        提前创建），则复用已有实例仅调用 :meth:`Plugin.initialize` 完成激活。
        """
        dir_name = metadata.root_dir_name
        if dir_name is None:
            raise CorePluginLoadException(metadata.name, "root_dir_name 为空")

        # —— 若实例已存在（由 _ensure_plugin_loaded 提前创建），
        #    复用实例仅完成异步初始化部分，避免重复创建导致路由冲突
        if metadata.plugin_instance is not None:
            await self._finish_activation(metadata)
            # _finish_activation 失败会抛出 CorePluginLoadException
            return

        plugin_path = os.path.join(self._plugin_dir, dir_name)

        # 安装依赖
        req = self._find_requirements(plugin_path)
        if req:
            self._install_requirements(req, metadata.name)

        # 导入模块
        module_file = self._find_main_module(plugin_path)
        if module_file is None:
            raise CorePluginLoadException(dir_name, "未找到 main.py")
        import_path = f"plugins.{dir_name}.{module_file}"
        project_root = (
            os.path.dirname(self._plugin_dir)
            if os.path.isabs(self._plugin_dir)
            else os.path.abspath(self._plugin_dir)
        )
        if project_root not in sys.path:
            sys.path.insert(0, project_root)
        module = importlib.import_module(import_path)

        # 查找 Plugin 子类
        plugin_cls = self._find_plugin_class(module, dir_name)

        # 加载配置
        plugin_config: dict = {}
        if metadata.config_schema_path and os.path.exists(metadata.config_schema_path):
            try:
                schema = PluginConfigManager.load_schema(metadata.config_schema_path)
                if schema:
                    plugin_config = self._config_mgr.load_config_with_defaults(
                        metadata.name, schema)
            except CorePluginConfigException as e:
                _log.warning("插件 [{}] 配置加载失败: {}", metadata.name, e)

        # 加载权限
        plugin_permissions = self._permission_mgr.ensure_permissions(metadata.name)

        # 实例化
        kwargs: dict = {}
        if plugin_permissions:
            kwargs["permissions"] = plugin_permissions
        instance = plugin_cls(**kwargs)

        # 注入属性
        instance.name = metadata.name
        instance.author = metadata.author
        instance.plugin_id = metadata.plugin_id
        data_dir = self.get_plugin_data_dir(metadata.name)
        instance.data_dir = data_dir

        # 更新元数据
        metadata.plugin_instance = instance
        metadata.module = module
        metadata.module_path = import_path
        metadata.config = plugin_config
        metadata.permissions = plugin_permissions
        metadata.data_dir = data_dir
        metadata.enabled = True

        # 注入 server 引用（若可用），供插件查询直播间列表等
        if self._server is not None:
            instance._server = self._server  # type: ignore[attr-defined]
        # 注入 PluginDataManager（封装 data 文件读写，路径沙箱）
        instance.data = PluginDataManager(data_dir)

        # 注册插件自定义路由（在 initialize 之前，确保 UI 立即可用）
        if self._app is not None and hasattr(instance, 'register_routes'):
            from fastapi import APIRouter as _APIRouter
            plugin_router = _APIRouter(prefix=f"/api/plugin/{metadata.name}/ui", tags=[metadata.name])
            instance.register_routes(plugin_router)
            PluginManager._insert_plugin_routes(self._app, plugin_router)
            metadata.routes_registered = True
            _log.info("插件已注册自定义 UI 路由: {}", metadata.name)

        # 初始化
        miss_config = MissConfig(plugin_config) if plugin_config else MissConfig({})
        try:
            await instance.initialize(config=miss_config)
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            _log.error("插件 [{}] 初始化失败，移入失败列表: {}", metadata.name, e)
            metadata.enabled = False
            metadata.initialized = False
            # 保留 plugin_instance 以便 UI 路由继续工作
            self._failed_plugins[dir_name] = {
                "dir_name": dir_name,
                "error": str(e),
                "traceback": tb,
            }
            self._notify_state_changed()
            raise CorePluginLoadException(
                metadata.name, f"插件初始化失败: {e}"
            )

        metadata.initialized = True
        self._event_bus.register_new_event(instance)
        _log.info("插件已激活并注册到事件总线: {}", metadata.name)

        # 注册 @command 指令
        if self._command_router is not None:
            self._command_router.register_plugin(instance)
            cmds = self._command_router.list_commands()
            names = cmds.get(metadata.name, [])
            if names:
                _log.info("插件已注册 {} 个指令: {}", len(names), names)

    async def enable_plugin(self, plugin_name: str) -> None:
        """启用插件——若尚未激活则完整加载（等待激活完成）。

        :raises CorePluginNotFoundException: 插件不存在
        :raises CorePluginLoadException: 插件初始化失败
        """
        metadata = self._get_plugin(plugin_name)
        if metadata.plugin_instance is not None and metadata.enabled:
            _log.info("插件已处于启用状态: {}", plugin_name)
            return

        self._disabled_plugins.discard(plugin_name)

        if metadata.plugin_instance is None:
            # 尚未激活 → 完整加载
            await self._activate_plugin(metadata)
        elif not metadata.initialized:
            # 实例已存在（由 _ensure_plugin_loaded 提前创建）但未初始化
            await self._finish_activation(metadata)
        else:
            # 实例存在且已初始化（如 suspend 后 resume）
            self._event_bus.register_new_event(metadata.plugin_instance)
            # 补注册指令
            if self._command_router is not None:
                self._command_router.register_plugin(metadata.plugin_instance)
            metadata.enabled = True

        _log.info("插件已启用: {}", plugin_name)

    def disable_plugin(self, plugin_name: str) -> None:
        """禁用插件。

        从事件总线和命令路由器取消注册，保留插件实例和文件。

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
            # 从命令路由器取消注册
            if self._command_router is not None:
                self._command_router.unregister_plugin(metadata.plugin_instance)
            # 调用终止钩子
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(metadata.plugin_instance.terminate())
            except RuntimeError:
                # 不在异步上下文中
                pass

        _log.info("插件已禁用: {}", plugin_name)

    def suspend_plugin(self, plugin_name: str) -> None:
        """暂停插件——取消事件注册和终止钩子，但不改变 enabled 标记。"""
        metadata = self._get_plugin(plugin_name)
        if metadata.plugin_instance is not None:
            self._event_bus.unregister_event(metadata.plugin_instance)
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(metadata.plugin_instance.terminate())
            except RuntimeError:
                pass
        _log.info("插件已暂停: {}", plugin_name)

    def resume_plugin(self, plugin_name: str) -> None:
        """恢复暂停的插件——同步完成路由注册，异步初始化。"""
        metadata = self._get_plugin(plugin_name)
        if metadata.plugin_instance is None:
            self._ensure_plugin_loaded(metadata)
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._finish_activation(metadata))
            except RuntimeError:
                pass
        elif not metadata.initialized:
            # 实例存在但从未初始化（由 set_app 提前加载）→ 异步完成初始化
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._finish_activation(metadata))
            except RuntimeError:
                pass
        else:
            self._event_bus.register_new_event(metadata.plugin_instance)
            # 补充注册路由（_app 可能在实例创建后才设置）
            self._register_routes_if_needed(metadata)
        _log.info("插件已恢复: {}", plugin_name)

    def _register_routes_if_needed(self, metadata: PluginMetadata) -> None:
        """为已有实例补注册 UI 路由（兜底：_app 延迟设置时）。

        若路由已注册（``metadata.routes_registered == True``）则跳过，
        避免 FastAPI 重复注册同一路由前缀。
        使用前端插入规避 SPA 兜底路由的拦截。
        """
        if metadata.routes_registered:
            return
        inst = metadata.plugin_instance
        if inst is not None and self._app is not None and hasattr(inst, 'register_routes'):
            from fastapi import APIRouter as _APIRouter
            plugin_router = _APIRouter(prefix=f"/api/plugin/{metadata.name}/ui", tags=[metadata.name])
            inst.register_routes(plugin_router)
            PluginManager._insert_plugin_routes(self._app, plugin_router)
            metadata.routes_registered = True
            _log.info("插件已补注册 UI 路由: {}", metadata.name)

    def _ensure_plugin_loaded(self, metadata: PluginMetadata) -> None:
        """同步加载插件模块并注册路由，不执行 initialize。"""
        dir_name = metadata.root_dir_name
        if not dir_name:
            return
        try:
            plugin_path = os.path.join(self._plugin_dir, dir_name)
            req = self._find_requirements(plugin_path)
            if req:
                self._install_requirements(req, metadata.name)
            module_file = self._find_main_module(plugin_path)
            if not module_file:
                _log.warning("插件 [{}] 未找到主模块，跳过加载", metadata.name)
                return
            import_path = f"plugins.{dir_name}.{module_file}"
            project_root = os.path.abspath(self._plugin_dir)
            if project_root not in sys.path:
                sys.path.insert(0, project_root)
            module = importlib.import_module(import_path)
            plugin_cls = self._find_plugin_class(module, dir_name)
            cfg: dict = {}
            if metadata.config_schema_path and os.path.exists(metadata.config_schema_path):
                try:
                    schema = PluginConfigManager.load_schema(metadata.config_schema_path)
                    if schema:
                        cfg = self._config_mgr.load_config_with_defaults(metadata.name, schema)
                except CorePluginConfigException:
                    pass
            perms = self._permission_mgr.ensure_permissions(metadata.name)
            kwargs: dict = {}
            if perms:
                kwargs["permissions"] = perms
            instance = plugin_cls(**kwargs)
            instance.name = metadata.name
            instance.author = metadata.author
            instance.plugin_id = metadata.plugin_id
            instance.data_dir = self.get_plugin_data_dir(metadata.name)
            if self._server is not None:
                instance._server = self._server  # type: ignore[attr-defined]
            instance.data = PluginDataManager(instance.data_dir)
            metadata.plugin_instance = instance
            metadata.module = module
            metadata.module_path = import_path
            metadata.config = cfg
            metadata.permissions = perms
            # 注册路由（插入到路由表前端以规避 SPA 兜底路由拦截）
            if self._app is not None and hasattr(instance, 'register_routes'):
                from fastapi import APIRouter as _APIRouter
                plugin_router = _APIRouter(prefix=f"/api/plugin/{metadata.name}/ui", tags=[metadata.name])
                instance.register_routes(plugin_router)
                PluginManager._insert_plugin_routes(self._app, plugin_router)
                metadata.routes_registered = True
                _log.info("插件已注册自定义 UI 路由: {}", metadata.name)
            elif hasattr(instance, 'register_routes'):
                _log.debug("插件 [{}] 有 register_routes 但 _app 未设置，将在 set_app 时补注册", metadata.name)
        except Exception as e:
            _log.error("插件 [{}] 同步加载失败: {}", metadata.name, e)

    async def _finish_activation(self, metadata: PluginMetadata) -> None:
        """完成插件的异步激活部分（调用 initialize + 注册到事件总线）。

        :raises CorePluginLoadException: 插件初始化失败
        """
        instance = metadata.plugin_instance
        if instance is None:
            return
        miss_config = MissConfig(metadata.config) if metadata.config else MissConfig({})
        try:
            await instance.initialize(config=miss_config)
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            _log.error("插件 [{}] 初始化失败，移入失败列表: {}", metadata.name, e)
            metadata.enabled = False
            metadata.initialized = False
            # 保留 plugin_instance/m/module 以便 UI 路由继续工作
            self._failed_plugins[metadata.root_dir_name or metadata.name] = {
                "dir_name": metadata.root_dir_name or metadata.name,
                "error": str(e),
                "traceback": tb,
            }
            self._notify_state_changed()
            raise CorePluginLoadException(
                metadata.name, f"插件初始化失败: {e}"
            )
        metadata.enabled = True
        metadata.initialized = True
        self._event_bus.register_new_event(instance)
        _log.info("插件已激活并注册到事件总线: {}", metadata.name)
        if self._command_router is not None:
            self._command_router.register_plugin(instance)
            cmds = self._command_router.list_commands()
            names = cmds.get(metadata.name, [])
            if names:
                _log.info("插件已注册 {} 个指令: {}", len(names), names)
        self._notify_state_changed()

    def suspend_all(self) -> None:
        """暂停所有已启用插件。"""
        for meta in list(self._plugins.values()):
            if meta.enabled and meta.plugin_instance is not None:
                try:
                    self.suspend_plugin(meta.name)
                except Exception:
                    pass

    def resume_all(self) -> None:
        """恢复所有标记为已启用的插件。"""
        for meta in list(self._plugins.values()):
            if meta.enabled:
                try:
                    self.resume_plugin(meta.name)
                except Exception:
                    pass

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

        流程：移除旧条目 → 重新加载元数据 → 若之前已启用则重新激活。
        激活成功才算重试成功。

        :param dir_name: 插件目录名
        :return: 插件元数据（已激活）
        :raises CorePluginLoadException: 重试仍然失败（加载或激活失败）
        :raises CorePluginNotFoundException: 插件不在失败列表
        """
        if dir_name not in self._failed_plugins:
            raise CorePluginNotFoundException(dir_name)

        # 先从 _plugins 中移除旧条目
        to_remove = [name for name, meta in self._plugins.items()
                     if meta.root_dir_name == dir_name]
        for name in to_remove:
            del self._plugins[name]
            _log.debug("已移除旧条目以重新加载: {}", name)

        self._failed_plugins.pop(dir_name, None)

        _log.info("正在重试加载插件: {}", dir_name)

        # 1. 重新加载元数据
        metadata = await self.load_plugin(dir_name)
        if metadata is None:
            raise CorePluginLoadException(dir_name, "load_plugin 返回 None")

        # 2. 重新激活（包含 initialize 调用），激活成功才算重试成功
        metadata.enabled = True
        try:
            await self._activate_plugin(metadata)
        except CorePluginLoadException:
            # _activate_plugin 已将失败记录到 _failed_plugins
            raise

        _log.info("插件重试成功: {}", metadata)
        self._notify_state_changed()
        return metadata  # type: ignore[return-value]

    def discard_failed_plugin(self, dir_name: str) -> None:
        """放弃加载失败的插件，将其回退到禁用状态。

        失败插件的元数据仍保留在插件列表中（``enabled=False``），
        可从失败筛选器中看到并可重试。目录文件保留不删除。

        :param dir_name: 插件目录名
        :raises CorePluginNotFoundException: 插件不在失败列表
        """
        if dir_name not in self._failed_plugins:
            raise CorePluginNotFoundException(dir_name)

        _log.info("放弃加载插件，回退到禁用状态: {}", dir_name)
        # 将插件设为禁用状态
        for meta in self._plugins.values():
            if meta.root_dir_name == dir_name:
                meta.enabled = False
                if meta.plugin_instance is not None:
                    self._unload_plugin_instance(meta)
        # 从失败列表移除
        self._failed_plugins.pop(dir_name, None)
        self._notify_state_changed()

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

        若旧路径（``data/{plugin_name}/``）存在而新路径不存在，
        自动迁移数据。

        :param plugin_name: 插件名称
        :return: 数据目录绝对路径
        """
        safe_name = plugin_name.replace("/", "_").replace("\\", "_")
        data_dir = os.path.join(self._plugin_data_dir, safe_name)

        # 迁移旧数据：data/{plugin_name}/ → data/plugins/{plugin_name}/
        if not os.path.exists(data_dir):
            old_dir = os.path.join(
                os.path.dirname(self._plugin_data_dir), safe_name
            )
            if os.path.isdir(old_dir):
                try:
                    shutil.move(old_dir, data_dir)
                    _log.info(
                        "插件数据已迁移: {} → {}", old_dir, data_dir
                    )
                except OSError as e:
                    _log.warning("插件数据迁移失败 [{}]: {}", plugin_name, e)

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

    @staticmethod
    def _insert_plugin_routes(app, plugin_router: "APIRouter") -> None:  # noqa: F821
        """将插件 UI 路由注册到 FastAPI，确保优先于 SPA 兜底路由。

        FastAPI/Starlette 按路由列表顺序匹配（先匹配者胜）。
        SPA 兜底路由 ``/{full_path:path}`` 在模块加载时已注册到列表末尾，
        若直接 ``include_router`` 会追加到兜底路由之后，导致请求被兜底路由拦截。

        此方法先暂存并移除兜底路由，再通过 ``include_router`` 以标准流程
        注册插件路由，最后将兜底路由恢复到列表末尾。
        """
        # 找到并暂存 SPA 兜底路由（避免它拦截插件 UI 请求）
        catch_all = None
        for i, route in enumerate(app.router.routes):
            if hasattr(route, 'path') and route.path == '/{full_path:path}':
                catch_all = app.router.routes.pop(i)
                break

        # 标准 FastAPI 路由注册（确保 APIRoute 正确初始化）
        app.include_router(plugin_router)

        # 将兜底路由放回末尾，使其优先级最低
        if catch_all is not None:
            app.router.routes.append(catch_all)

    def _notify_state_changed(self) -> None:
        """通知外部（如 Server）插件状态已变更，需要持久化。"""
        if self._on_state_changed is not None:
            self._on_state_changed()

    def _unload_plugin_instance(self, metadata: PluginMetadata) -> None:
        """终止并取消注册一个插件实例。

        :param metadata: 插件元数据
        """
        instance = metadata.plugin_instance
        if instance is None:
            return  # 未激活的插件无需卸载

        # 从事件总线取消注册
        self._event_bus.unregister_event(instance)

        # 从命令路由器取消注册
        if self._command_router is not None:
            self._command_router.unregister_plugin(instance)

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

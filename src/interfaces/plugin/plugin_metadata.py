"""插件元数据。

定义插件的描述性信息数据结构。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import ModuleType
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from interfaces.plugin.plugin import Plugin


@dataclass
class PluginMetadata:
    """插件元数据。

    在插件加载时从 ``metadata.yaml`` 读取基本信息，
    运行时字段由 :class:`PluginManager` 填充。

    .. versionadded:: 1.1
    """

    # ---------------------------------------------------------------- #
    # 声明字段（来自 metadata.yaml）
    # ---------------------------------------------------------------- #

    name: str
    """插件名称（唯一标识）。"""

    author: str
    """插件作者。"""

    desc: str
    """插件简介。"""

    version: str
    """插件版本号。"""

    # ---------------------------------------------------------------- #
    # 可选声明字段（来自 metadata.yaml）
    # ---------------------------------------------------------------- #

    short_desc: str | None = None
    """插件简短描述。"""

    repo: str | None = None
    """插件仓库 URL（如 GitHub 地址）。"""

    display_name: str | None = None
    """插件显示名称（用于 UI 展示）。"""

    # ---------------------------------------------------------------- #
    # 运行时字段（由 PluginManager 填充）
    # ---------------------------------------------------------------- #

    module_path: str | None = None
    """插件模块的完整 Python 导入路径，如 ``plugins.my_plugin.main``。"""

    module: ModuleType | None = field(default=None, compare=False, repr=False)
    """插件模块对象。"""

    plugin_instance: "Plugin | None" = field(
        default=None, compare=False, repr=False
    )
    """插件实例，未激活时为 ``None``。"""

    root_dir_name: str | None = None
    """插件根目录名（即 ``plugins/`` 下的文件夹名称）。"""

    enabled: bool = True
    """是否已启用。"""

    config_schema_path: str | None = None
    """``_conf_schema.json`` 的绝对路径，若不存在则为 ``None``。"""

    config: dict | None = field(default=None, compare=False)
    """插件运行时配置（已合并默认值）。"""

    permission_config: dict | None = field(default=None, compare=False)
    """插件权限配置。"""

    readme_path: str | None = None
    """``README.md`` 的绝对路径，若不存在则为 ``None``。"""

    requirements_path: str | None = None
    """``requirements.txt`` 的绝对路径，若不存在则为 ``None``。"""

    data_dir: str | None = None
    """插件专属数据目录（``data/{plugin_name}/``），插件加载时自动创建。"""

    # ---------------------------------------------------------------- #
    # 计算属性
    # ---------------------------------------------------------------- #

    @property
    def plugin_id(self) -> str:
        """返回 ``{author}/{name}`` 格式的唯一标识。

        与 AstrBot 兼容的插件 ID 格式，用于跨项目引用。
        """
        author_lower = self.author.lower().strip()
        name_lower = self.name.lower().strip()
        return f"{author_lower}/{name_lower}"

    # ---------------------------------------------------------------- #
    # dunder
    # ---------------------------------------------------------------- #

    def __str__(self) -> str:
        return f"{self.name} v{self.version} by {self.author}"

    def __repr__(self) -> str:
        return f"PluginMetadata(name={self.name!r}, version={self.version!r})"

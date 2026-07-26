"""插件数据文件管理器。

为每个插件提供隔离的数据文件访问接口，确保所有读写操作
限定在插件的专属数据目录内（路径沙箱）。插件应通过该管理器
而非直接文件操作来读写持久化数据，为未来沙箱化奠定基础。
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

from core.logging import get_logger

_log = get_logger(__name__)


class PluginDataManager:
    """插件数据文件管理器。

    封装插件 data 文件的创建、读取、写入、删除操作，
    所有路径自动限定在插件的专属数据目录内（``{plugin_data_dir}/{plugin_name}/``）。

    用法::

        # Plugin.initialize 中通过参数接收
        async def initialize(self, config: MissConfig, data: PluginDataManager) -> None:
            songs = data.read_json("playlist.json") or []
            data.write_json("playlist.json", songs)

    .. versionadded:: 1.3
    """

    __slots__ = ("_data_dir",)

    def __init__(self, data_dir: str) -> None:
        self._data_dir: str = os.path.abspath(data_dir)
        Path(self._data_dir).mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    # 属性
    # ------------------------------------------------------------------ #

    @property
    def data_dir(self) -> str:
        """插件数据目录的绝对路径（只读）。"""
        return self._data_dir

    # ------------------------------------------------------------------ #
    # JSON 读写（最常用）
    # ------------------------------------------------------------------ #

    def read_json(self, filename: str) -> Any:
        """读取 JSON 文件并返回解析后的对象。

        :param filename: 相对于数据目录的文件名（如 ``"playlist.json"``）
        :return: 解析后的 Python 对象；文件不存在或解析失败返回 ``None``
        """
        path = self._resolve(filename)
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return None
        except json.JSONDecodeError as e:
            _log.warning("JSON 解析失败 [{}]: {}", filename, e)
            return None

    def write_json(self, filename: str, data: Any) -> None:
        """将数据序列化为 JSON 并写入文件。

        自动创建父目录（如需要）。

        :param filename: 相对于数据目录的文件名
        :param data: 要序列化的 Python 对象
        :raises OSError: 写入失败
        """
        path = self._resolve(filename)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ------------------------------------------------------------------ #
    # 纯文本读写
    # ------------------------------------------------------------------ #

    def read_text(self, filename: str) -> str | None:
        """读取纯文本文件。

        :return: 文件内容字符串；文件不存在返回 ``None``
        """
        path = self._resolve(filename)
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            return None

    def write_text(self, filename: str, content: str) -> None:
        """写入纯文本文件（覆盖模式）。

        :raises OSError: 写入失败
        """
        path = self._resolve(filename)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    # ------------------------------------------------------------------ #
    # 文件管理
    # ------------------------------------------------------------------ #

    def delete(self, filename: str) -> None:
        """删除指定文件（目录则递归删除）。

        文件不存在时不报错。
        """
        path = self._resolve(filename)
        try:
            if os.path.isdir(path):
                shutil.rmtree(path)
            elif os.path.isfile(path):
                os.remove(path)
        except OSError as e:
            _log.warning("删除文件失败 [{}]: {}", filename, e)

    def exists(self, filename: str) -> bool:
        """检查文件或目录是否存在。"""
        return os.path.exists(self._resolve(filename))

    # ------------------------------------------------------------------ #
    # 内部
    # ------------------------------------------------------------------ #

    def _resolve(self, filename: str) -> str:
        """解析文件路径，校验不逃逸 data_dir（路径沙箱）。

        :raises ValueError: 路径企图逃逸数据目录
        """
        # 拒绝绝对路径和 .. 逃逸（在规范化后检测）
        full = os.path.normpath(os.path.join(self._data_dir, filename))
        norm_root = os.path.normpath(self._data_dir)
        if not full.startswith(norm_root + os.sep) and full != norm_root:
            raise ValueError(
                f"插件数据文件路径逃逸: '{filename}' → '{full}' "
                f"(数据目录: {norm_root})"
            )
        return full

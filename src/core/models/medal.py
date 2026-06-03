"""粉丝勋章数据类。

``Medal`` 接口的具体实现。
"""

from dataclasses import dataclass

from interfaces.entity.medal import Medal


@dataclass
class RoomMedal(Medal):
    """直播间粉丝勋章。

    实现 :class:`Medal` 接口的值对象。
    """

    medal_name: str
    medal_level: int

    @property
    def name(self) -> str:
        """勋章名称。"""
        return self.medal_name

    @property
    def level(self) -> int:
        """勋章等级。"""
        return self.medal_level

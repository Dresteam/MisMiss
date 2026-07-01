"""Missevan 机器人实现。

提供 ``Bot`` 接口的完整实现，封装 Missevan 机器人的消息发送、
背包查询和礼物赠送操作。
"""

from __future__ import annotations

import asyncio
from collections import namedtuple
from typing import TYPE_CHECKING, Optional

from interfaces.bot.bot import Bot, BotPermission
from interfaces.entity.gift import Gift
from interfaces.plugin.plugin import current_plugin
from ..logging import get_logger
from ..exceptions import (
    CoreApiException,
    CoreCookieException,
    CoreDisabledException,
    CorePermissionException,
)
from ..models.gift import BotGift
from ..network.endpoints.backpack import BackpackSendAPI
from ..network.endpoints.bot_info import BotInfoAPI
from ..network.endpoints.bot_status import BotStatusAPI
from ..network.endpoints.gift import GiftSendAPI
from ..network.endpoints.message import MessageSendAPI
from ..network.endpoints.online import OnlineAPI

if TYPE_CHECKING:
    pass

# 内部使用的消息条目
_MessageItem = namedtuple("_MessageItem", ["priority", "live_id", "message"])

_log = get_logger(__name__)

# 默认权限
_DEFAULT_PERMISSIONS: BotPermission = BotPermission.SEND_LIVESTREAM_MESSAGE


class MissevanBot(Bot):
    """Missevan 机器人。

    实现 :class:`Bot` 接口，使用 Cookie 认证与 Missevan API 交互。

    消息发送采用 **优先级队列** 机制：
    所有待发送消息加入内部队列并按优先级（由大到小）排序，
    由后台消费者依次处理，每条消息发送后等待 100ms 防止请求被限。

    用法::

        bot = MissevanBot(cookie="your_cookie_here")
        await bot.send_livestream_message(12345, "Hello!", priority=10)

    :param cookie: Missevan 登录 Cookie
    :raises CoreCookieException: Cookie 无效或已过期
    """

    def __init__(
        self,
        cookie: str,
        *,
        permissions: BotPermission = _DEFAULT_PERMISSIONS,
    ) -> None:
        self.__cookie = cookie

        # 延迟初始化 — 仅在首次需要时获取
        self._id: int = 0
        self._name: str = ""
        self._introduction: str = ""
        self._icon_url: str = ""
        self._initialized: bool = False

        # 消息队列 + 消费者
        self._message_queue: list[_MessageItem] = []
        self._queue_lock = asyncio.Lock()
        self._consumer_task: asyncio.Task[None] | None = None

        # 权限：创建后不可修改
        self.__permissions: BotPermission = permissions
        # 启用状态
        self._enabled: bool = True

    # ------------------------------------------------------------------ #
    # 启停控制
    # ------------------------------------------------------------------ #

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value

    def _check_enabled(self) -> None:
        """检查是否已启用，停用时抛出异常。

        :raises CoreDisabledException: 功能已停用
        """
        if not self._enabled:
            raise CoreDisabledException("机器人已停用")

    # ------------------------------------------------------------------ #
    # 权限控制
    # ------------------------------------------------------------------ #

    @property
    def permissions(self) -> BotPermission:
        """权限集合（只读——创建后不可修改）。"""
        return self.__permissions

    def _check_permission(self, perm: BotPermission) -> None:
        """检查是否拥有指定权限，不足则抛出异常。

        :param perm: 所需权限
        :raises CorePermissionException: 权限不足
        """
        if not (self.__permissions & perm):
            raise CorePermissionException(
                f"权限不足：缺少 {perm.name}",
                required=str(perm.name),
            )

    def _check_plugin_permission(self, perm: BotPermission) -> None:
        """校验当前插件是否拥有指定权限。

        通过 :data:`current_plugin` 上下文变量获取正在执行事件处理器
        的插件实例。若非插件调用（如 Server 直接调用），静默通过。

        :param perm: 所需权限
        :raises CorePermissionException: 插件缺乏该权限
        """
        plugin = current_plugin.get()
        if plugin is None or plugin.permissions is None:
            return  # 非插件调用或插件无权限配置，静默通过

        perm_name = perm.name
        if not plugin.permissions.get(perm_name, False):
            raise CorePermissionException(
                f"插件 '{plugin.name}' 缺少 {perm_name} 权限",
                required=perm_name,
            )

    # ------------------------------------------------------------------ #
    # User 属性
    # ------------------------------------------------------------------ #

    @property
    def name(self) -> str:
        return self._name

    @property
    def id(self) -> int:
        return self._id

    @property
    def introduction(self) -> Optional[str]:
        return self._introduction or ""

    @property
    def icon_url(self) -> Optional[str]:
        return self._icon_url or ""

    # ------------------------------------------------------------------ #
    # 刷新
    # ------------------------------------------------------------------ #

    async def refresh(self) -> None:
        """刷新机器人信息并验证 Cookie 状态。

        从 Missevan API 重新获取用户资料，同时检查 Cookie 是否有效。
        Cookie 过期时自动将机器人设为停用状态。

        可在创建实例后直接调用，也可通过 :meth:`_ensure_initialized` 自动触发。

        :raises CoreCookieException: Cookie 已过期
        """

        response = self._check_success(await BotInfoAPI(self.__cookie).api())
        info = response.get("info", {}).get("user", {})
        if not info:
            self.enabled = False
            raise CoreCookieException("Cookie 已过期")

        self._id = info.get("user_id", 0)
        self._name = info.get("username", "")
        self._introduction = info.get("introduction", "")
        self._icon_url = info.get("iconurl", "")
        self._initialized = True

    # ------------------------------------------------------------------ #
    # API 调用包装
    # ------------------------------------------------------------------ #

    async def _safe_call(self, factory):
        """包装 API 调用——失败时自动检查 Cookie 状态并校验返回值。

        当 API 调用因 :class:`CoreApiException` 失败时，
        自动调用 :meth:`refresh` 检查 Cookie：
        - 若 Cookie 过期则 bot 自动停用
        - 无论刷新成败，均重新抛出原始异常

        :param factory: 返回 awaitable 的无参工厂函数
        :return: API 返回值（已通过 :meth:`_check_success` 校验）
        :raises CoreApiException: 原始 API 异常
        :raises CoreCookieException: Cookie 已过期（bot 已自动停用）
        """
        try:
            result = await factory()
            return self._check_success(result)
        except CoreApiException:
            await self.refresh()
            raise

    # ------------------------------------------------------------------ #
    # Bot 接口实现
    # ------------------------------------------------------------------ #

    async def send_livestream_message(
        self, live_id: int, message: str, priority: int = 0
    ) -> None:
        """向指定直播间发送消息（优先级队列）。

        需要权限 :attr:`~BotPermission.SEND_LIVESTREAM_MESSAGE`。

        :param live_id: 直播间 ID
        :param message: 消息文本
        :param priority: 优先级（值越大越优先），默认为 0
        :raises CorePermissionException: 权限不足
        """
        self._check_enabled()
        self._check_permission(BotPermission.SEND_LIVESTREAM_MESSAGE)
        self._check_plugin_permission(BotPermission.SEND_LIVESTREAM_MESSAGE)
        await self._ensure_initialized()

        async with self._queue_lock:
            self._message_queue.append(
                _MessageItem(priority=priority, live_id=live_id, message=message)
            )
            # 按优先级由大到小排序
            self._message_queue.sort(key=lambda x: x.priority, reverse=True)

            # 如果消费者未运行则启动
            consumer_idle = (
                self._consumer_task is None or self._consumer_task.done()
            )
            if consumer_idle:
                self._consumer_task = asyncio.create_task(self._consume_queue())
                _log.debug(
                    "消费者已启动 直播间={} 队列长度={}", live_id, len(self._message_queue)
                )
            else:
                _log.debug(
                    "消息已入队 直播间={} 队列长度={}（消费者运行中）",
                    live_id,
                    len(self._message_queue),
                )

    # ------------------------------------------------------------------ #
    # 消息队列消费者
    # ------------------------------------------------------------------ #

    async def _consume_queue(self) -> None:
        """消费队列中的一条消息，处理完毕后若队列非空则自动续调。

        每次取优先级最高的一条消息发送，发送后等待 100ms，
        然后检查队列是否还有剩余条目：有则重新调度自身，
        无则自然退出。不依赖 ``while True`` 死循环。

        调用方（:meth:`send_livestream_message`）仅在消费者
        未运行时才会启动新的消费任务。
        """
        try:
            # 取一条消息
            async with self._queue_lock:
                if not self._message_queue:
                    _log.debug("消费者退出：队列为空")
                    return
                item = self._message_queue.pop(0)
                _log.info(
                    "发送消息 直播间={} 内容={} 优先级={} 剩余={}",
                    item.live_id,
                    item.message,
                    item.priority,
                    len(self._message_queue),
                )

            # 发送（失败不阻塞后续消息，包内自动检查 Cookie）
            try:
                await self._safe_call(
                    lambda: MessageSendAPI(self.__cookie).api(
                        item.live_id, item.message
                    )
                )
            except CoreApiException as e:
                _log.warning(
                    "消息发送失败 直播间={} 内容={} 原因={}",
                    item.live_id,
                    item.message,
                    e,
                )
            except CoreCookieException:
                _log.error("Cookie 已过期，清空消息队列（{} 条）",
                           len(self._message_queue) + 1)
                async with self._queue_lock:
                    self._message_queue.clear()
                return  # Cookie 过期后不再续调

            # 发送间隔，防止请求过于频繁
            await asyncio.sleep(0.1)

            # 判断队列是否还有剩余，有则续调自身
            async with self._queue_lock:
                has_more = bool(self._message_queue)

            if has_more:
                self._consumer_task = asyncio.create_task(self._consume_queue())
            else:
                _log.debug("消费者退出：队列已清空")
        except Exception:
            _log.exception("消费者发生未预期异常，任务终止")

    async def send_private_message(self, user_id: int, message: str) -> None:
        """向指定用户发送私信（后续扩展）。

        需要权限 :attr:`~BotPermission.SEND_PRIVATE_MESSAGE`。

        :param user_id: 目标用户 ID
        :param message: 信息文本
        :raises CorePermissionException: 权限不足
        """
        self._check_enabled()
        self._check_permission(BotPermission.SEND_PRIVATE_MESSAGE)
        self._check_plugin_permission(BotPermission.SEND_PRIVATE_MESSAGE)
        await self._ensure_initialized()
        # TODO: 后续接入私信 API
        raise NotImplementedError("私信功能尚未实现")

    async def get_backpack_gifts(self, live_id: int) -> list[Gift]:
        """获取机器人背包礼物列表。

        先登录房间刷新背包状态，再获取背包礼物。

        :param live_id: 直播间 ID（用于刷新背包状态）
        :return: 背包礼物列表
        """
        self._check_enabled()
        await self._ensure_initialized()

        # 登录房间 — 刷新背包状态
        await self._safe_call(lambda: OnlineAPI(self.__cookie).api(live_id))

        # 获取背包
        response = await self._safe_call(
            lambda: BotStatusAPI(self.__cookie).api()
        )

        info = response.get("info", {})
        backpack = info.get("backpack", [])
        if not isinstance(backpack, list):
            return []

        gifts: list[Gift] = []
        for item in backpack:
            if not isinstance(item, dict):
                continue
            gifts.append(BotGift(
                gift_bot=self,
                gift_id=item.get("gift_id", 0),
                gift_name=item.get("name", ""),
                gift_price=item.get("price", 0),
                gift_num=item.get("num", 0),
            ))
        return gifts

    async def send_livestream_gift(self, live_id: int, gift_id: int, num: int) -> None:
        """向直播间赠送直售礼物。

        需要权限 :attr:`~BotPermission.SEND_GIFT`。

        :param live_id: 直播间 ID
        :param gift_id: 礼物 ID
        :param num: 礼物数量
        :raises CorePermissionException: 权限不足
        """
        self._check_enabled()
        self._check_permission(BotPermission.SEND_GIFT)
        self._check_plugin_permission(BotPermission.SEND_GIFT)
        await self._ensure_initialized()
        await self._safe_call(
            lambda: GiftSendAPI(self.__cookie).api(live_id, gift_id, num)
        )

    async def send_livestream_backpack(self, live_id: int, gift_id: int, num: int) -> None:
        """向直播间赠送背包内礼物。

        需要权限 :attr:`~BotPermission.SEND_BACKPACK_GIFT`。

        :param live_id: 直播间 ID
        :param gift_id: 背包礼物 ID
        :param num: 礼物数量
        :raises CorePermissionException: 权限不足
        """
        self._check_enabled()
        self._check_permission(BotPermission.SEND_BACKPACK_GIFT)
        self._check_plugin_permission(BotPermission.SEND_BACKPACK_GIFT)
        await self._ensure_initialized()
        await self._safe_call(
            lambda: BackpackSendAPI(self.__cookie).api(live_id, gift_id, num)
        )

    def get_cookie(self) -> str:
        """获取机器人的 Cookie 字符串。

        需要权限 :attr:`~BotPermission.EXPOSE_COOKIE`。
        这是唯一暴露 Cookie 的入口。

        :return: Cookie 字符串
        :raises CorePermissionException: 权限不足
        """
        self._check_enabled()
        self._check_permission(BotPermission.EXPOSE_COOKIE)
        self._check_plugin_permission(BotPermission.EXPOSE_COOKIE)
        return self.__cookie

    # ------------------------------------------------------------------ #
    # 辅助方法
    # ------------------------------------------------------------------ #

    def __repr__(self) -> str:
        return f"MissevanBot(id={self._id})"

    async def _ensure_initialized(self) -> None:
        """确保已初始化，未初始化时自动调用 :meth:`refresh`。"""
        if not self._initialized:
            await self.refresh()

    @staticmethod
    def _check_success(response: dict) -> dict:
        """检查 API 响应是否成功（code == 0）。

        :param response: API 响应 JSON
        :return: 原始响应（用于链式调用）
        :raises CoreApiException: 响应 code 非 0 或响应为空
        """
        if not response:
            raise CoreApiException("请求失败：空响应")
        if response.get("code") != 0:
            raise CoreApiException(
                f"请求失败: {response.get('info', '未知错误')}"
            )
        return response

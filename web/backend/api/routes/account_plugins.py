"""账户级插件路由 —— 从插件库启用/停用/配置本账户的插件实例。

挂载于 ``/api/accounts/{account_id}/plugins``。
插件库的安装/卸载/刷新走面板级 ``/api/plugin``。
"""

from __future__ import annotations

import json
import os

from fastapi import APIRouter, Depends, HTTPException

from core import MissevanServer
from core.exceptions import (
    CorePluginConfigException,
    CorePluginLoadException,
    CorePluginNotFoundException,
    CorePluginPermissionException,
)
from api.deps import require_account, require_active_account
from api.schemas import (
    PluginConfigUpdateRequest,
    PluginDetailResponse,
    PluginEventHandler,
    PluginPermissionInfo,
    PluginPermUpdateRequest,
    PluginSummary,
    StatusResponse,
)

router = APIRouter()


# ------------------------------------------------------------------ #
# 辅助
# ------------------------------------------------------------------ #

def _plugin_to_summary(meta) -> PluginSummary:
    return PluginSummary(
        name=meta.name,
        plugin_id=meta.plugin_id,
        author=meta.author,
        version=meta.version,
        display_name=meta.display_name,
        short_desc=meta.short_desc,
        desc=meta.desc,
        enabled=meta.enabled,
        has_config=meta.config_schema_path is not None,
        has_readme=meta.readme_path is not None,
        has_ui=meta.ui_schema_path is not None,
        has_changelog=bool(
            meta.module_path and
            os.path.exists(
                os.path.join(
                    os.path.dirname(meta.module_path.replace(".", "/")),
                    "CHANGELOG.md",
                )
            )
        ),
    )


def _plugin_to_detail(s: MissevanServer, meta) -> PluginDetailResponse:
    """构建插件详情（含 handlers、permissions、config schema/values）。"""
    handlers: list[PluginEventHandler] = []
    try:
        raw_handlers = s.list_plugin_handlers(meta.name)
        for method_name, event_type in raw_handlers.items():
            handlers.append(PluginEventHandler(
                method_name=method_name,
                event_type=event_type.__name__,
            ))
    except Exception:
        pass

    permissions: dict | None = None
    try:
        perm_info = s.get_plugin_permissions(meta.name)
        permissions = perm_info.get("permissions")
    except Exception:
        pass

    config_schema = None
    config_values = None
    try:
        config_schema = s.get_plugin_config_schema(meta.name)
        if config_schema and meta.config:
            config_values = meta.config
    except Exception:
        pass

    ui_schema = None
    if meta.ui_schema_path:
        try:
            with open(meta.ui_schema_path, "r", encoding="utf-8") as f:
                ui_schema = json.load(f)
        except Exception:
            pass

    return PluginDetailResponse(
        name=meta.name,
        plugin_id=meta.plugin_id,
        author=meta.author,
        version=meta.version,
        display_name=meta.display_name,
        short_desc=meta.short_desc,
        desc=meta.desc,
        repo=meta.repo,
        enabled=meta.enabled,
        has_config=meta.config_schema_path is not None,
        has_readme=meta.readme_path is not None,
        has_changelog=_plugin_to_summary(meta).has_changelog,
        handlers=handlers,
        permissions=permissions,
        config_schema=config_schema,
        config_values=config_values,
        ui_schema=ui_schema,
    )


# ================================================================== #
# 路由 —— 插件库(账户可安装列表)
# ================================================================== #


@router.get("/library")
async def plugin_library(account_id: int, s: MissevanServer = Depends(require_account)):
    """账户可安装的插件库列表(含是否已安装)。"""
    from api.deps import get_account_manager
    return get_account_manager().list_available_plugins(account_id)


@router.post("/install", response_model=StatusResponse)
async def plugin_install_to_account(
    account_id: int, body: dict, s: MissevanServer = Depends(require_active_account)
):
    """从插件库安装插件到账户(拷贝源码副本独立运行,安装后默认停用)。"""
    plugin_name = str(body.get("name", "")).strip()
    if not plugin_name:
        raise HTTPException(status_code=400, detail="必须指定插件名")
    from api.deps import get_account_manager
    try:
        await get_account_manager().install_plugin_to_account(account_id, plugin_name)
        return StatusResponse(success=True, message=f"插件 '{plugin_name}' 已安装到账户(默认停用)")
    except CorePluginNotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{plugin_name}/update", response_model=StatusResponse)
async def plugin_update_from_library(
    plugin_name: str, account_id: int, s: MissevanServer = Depends(require_active_account)
):
    """从插件库更新账户插件副本:覆盖源码并重载,保留启用状态与既有配置。

    新版本配置 schema 新增的字段自动补默认值。
    """
    from api.deps import get_account_manager
    try:
        await get_account_manager().update_plugin_in_account(account_id, plugin_name)
        return StatusResponse(success=True, message=f"插件 '{plugin_name}' 已更新到库版本")
    except CorePluginNotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))
    except CorePluginLoadException as e:
        raise HTTPException(status_code=500, detail=str(e))


# ================================================================== #
# 路由 —— 列表 & 详情
# ================================================================== #


@router.get("/", response_model=list[PluginSummary])
async def plugin_list(account_id: int, s: MissevanServer = Depends(require_account)):
    """账户已安装插件列表(含本账户启用状态)。"""
    await s._ensure_bot_restored()
    plugins = s.plugins
    return [_plugin_to_summary(p) for p in plugins]


@router.delete("/{plugin_name}", response_model=StatusResponse)
async def plugin_uninstall_from_account(
    account_id: int,
    plugin_name: str,
    delete_config: bool = False,
    delete_data: bool = False,
    s: MissevanServer = Depends(require_active_account),
):
    """账户卸载插件:停止实例、删除源码副本(可选清除配置/数据)。"""
    from api.deps import get_account_manager
    try:
        await get_account_manager().uninstall_plugin_from_account(
            account_id, plugin_name, delete_config=delete_config, delete_data=delete_data
        )
        return StatusResponse(success=True, message=f"插件 '{plugin_name}' 已从账户卸载")
    except CorePluginNotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{plugin_name}", response_model=PluginDetailResponse)
async def plugin_info(plugin_name: str, account_id: int, s: MissevanServer = Depends(require_account)):
    """获取账户内插件详情。"""
    pm = s._plugin_manager
    meta = pm.get_plugin(plugin_name)
    if meta is None:
        raise HTTPException(status_code=404, detail=f"插件 '{plugin_name}' 不存在")
    return _plugin_to_detail(s, meta)


@router.get("/{plugin_name}/handlers", response_model=list[PluginEventHandler])
async def plugin_handlers(
    plugin_name: str, account_id: int, s: MissevanServer = Depends(require_account)
):
    """获取插件的事件处理器列表。"""
    try:
        raw = s.list_plugin_handlers(plugin_name)
        return [
            PluginEventHandler(method_name=m, event_type=e.__name__)
            for m, e in raw.items()
        ]
    except CorePluginNotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))


# ================================================================== #
# 路由 —— 启停 & 重载
# ================================================================== #


@router.post("/{plugin_name}/enable", response_model=StatusResponse)
async def plugin_enable(
    plugin_name: str, account_id: int, s: MissevanServer = Depends(require_active_account)
):
    """启用插件——完成完整加载流程（含异步初始化）。"""
    try:
        await s.enable_plugin(plugin_name)
        return StatusResponse(success=True, message=f"插件 '{plugin_name}' 已启用")
    except CorePluginNotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))
    except CorePluginLoadException as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{plugin_name}/disable", response_model=StatusResponse)
async def plugin_disable(
    plugin_name: str, account_id: int, s: MissevanServer = Depends(require_active_account)
):
    """禁用插件——从事件总线和命令路由器取消注册。"""
    try:
        await s.disable_plugin(plugin_name)
        s._save_state()
        return StatusResponse(success=True, message=f"插件 '{plugin_name}' 已禁用")
    except CorePluginNotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{plugin_name}/reload", response_model=PluginSummary)
async def plugin_reload(
    plugin_name: str, account_id: int, s: MissevanServer = Depends(require_active_account)
):
    """重载插件（保留启停状态）。"""
    try:
        pm = s._plugin_manager
        was_enabled = pm.get_plugin(plugin_name).enabled
        pm.suspend_plugin(plugin_name)
        meta = await pm.reload_plugin(plugin_name)
        meta.enabled = was_enabled  # 恢复原标记
        if was_enabled and s.bot_available:
            pm.resume_plugin(plugin_name)
        s._save_state()
        return _plugin_to_summary(meta)
    except CorePluginNotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))
    except CorePluginLoadException as e:
        raise HTTPException(status_code=500, detail=str(e))


# ================================================================== #
# 路由 —— 权限
# ================================================================== #


@router.get("/{plugin_name}/permissions", response_model=PluginPermissionInfo)
async def plugin_permissions(
    plugin_name: str, account_id: int, s: MissevanServer = Depends(require_account)
):
    """获取插件的权限配置（含生效状态）。"""
    try:
        info = s.get_plugin_permissions(plugin_name)
        return PluginPermissionInfo(**info)
    except CorePluginNotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/{plugin_name}/permissions", response_model=StatusResponse)
async def plugin_update_permission(
    plugin_name: str,
    account_id: int,
    req: PluginPermUpdateRequest,
    s: MissevanServer = Depends(require_active_account),
):
    """更新插件单个权限项。"""
    try:
        s.update_plugin_permission(plugin_name, req.key, req.value)
        return StatusResponse(
            success=True,
            message=f"{plugin_name}.{req.key} = {req.value}",
        )
    except CorePluginNotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))
    except CorePluginPermissionException as e:
        raise HTTPException(status_code=400, detail=str(e))


# ================================================================== #
# 路由 —— 配置
# ================================================================== #


@router.get("/{plugin_name}/config")
async def plugin_get_config(
    plugin_name: str, account_id: int, s: MissevanServer = Depends(require_account)
):
    """获取插件的配置 schema 及当前值。"""
    try:
        schema = s.get_plugin_config_schema(plugin_name)
        pm = s._plugin_manager
        meta = pm.get_plugin(plugin_name)
        return {
            "schema": schema,
            "values": meta.config if meta else {},
        }
    except CorePluginNotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/{plugin_name}/config", response_model=StatusResponse)
async def plugin_update_config(
    plugin_name: str,
    account_id: int,
    req: PluginConfigUpdateRequest,
    s: MissevanServer = Depends(require_active_account),
):
    """更新插件配置。若插件运行中，保存后立即重载以热加载配置。"""
    pm = s._plugin_manager
    meta = pm.get_plugin(plugin_name)
    if meta is None:
        raise HTTPException(status_code=404, detail=f"插件 '{plugin_name}' 不存在")
    try:
        pm.config_manager.save_config(plugin_name, req.config)
        meta.config = req.config

        reloaded = False
        if meta.enabled and meta.plugin_instance is not None:
            try:
                await pm.reload_plugin(plugin_name)
                meta = pm.get_plugin(plugin_name)
                if meta:
                    meta.enabled = True
                    await pm.enable_plugin(plugin_name)
                reloaded = True
            except Exception as e:
                import logging
                logging.getLogger("api.account_plugins").warning(
                    "配置保存后重载插件失败 [%s]: %s", plugin_name, e
                )

        msg = f"配置已保存: {plugin_name}" + ("（已热重载）" if reloaded else "")
        return StatusResponse(success=True, message=msg)
    except CorePluginConfigException as e:
        raise HTTPException(status_code=500, detail=str(e))


# ================================================================== #
# 路由 —— README / CHANGELOG
# ================================================================== #


@router.get("/{plugin_name}/readme")
async def plugin_readme(
    plugin_name: str, account_id: int, s: MissevanServer = Depends(require_account)
):
    """获取插件的 README.md 内容。"""
    try:
        content = s.get_plugin_readme(plugin_name)
        return {"content": content or "", "plugin_name": plugin_name}
    except CorePluginNotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{plugin_name}/changelog")
async def plugin_changelog(
    plugin_name: str, account_id: int, s: MissevanServer = Depends(require_account)
):
    """获取插件的 CHANGELOG.md 内容。"""
    try:
        content = s.get_plugin_changelog(plugin_name)
        return {"content": content or "", "plugin_name": plugin_name}
    except CorePluginNotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{plugin_name}/changelog")
async def plugin_changelog(
    plugin_name: str, account_id: int, s: MissevanServer = Depends(require_account)
):
    """获取插件的 CHANGELOG.md 内容。"""
    try:
        content = s.get_plugin_changelog(plugin_name)
        return {"content": content or "", "plugin_name": plugin_name}
    except CorePluginNotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))

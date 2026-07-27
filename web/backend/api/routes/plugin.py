"""插件管理 API 路由。

包含插件生命周期、权限、配置、README/CHANGELOG 等全部端点。
"""

from __future__ import annotations

import os
import tempfile
import shutil
import zipfile
import yaml

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File

from core import MissevanServer
from core.exceptions import (
    CorePluginNotFoundException,
    CorePluginPermissionException,
    CorePluginLoadException,
    CorePluginConfigException,
)
from api.deps import get_server
from api.schemas import (
    PluginSummary,
    PluginDetailResponse,
    PluginEventHandler,
    PluginPermissionInfo,
    PluginPermUpdateRequest,
    PluginConfigUpdateRequest,
    FailedPluginInfo,
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
            __import__("os").path.exists(
                __import__("os").path.join(
                    __import__("os").path.dirname(meta.module_path.replace(".", "/")),
                    "CHANGELOG.md",
                )
            )
        ),
    )


def _plugin_to_detail(s: MissevanServer, meta) -> PluginDetailResponse:
    """构建插件详情（含 handlers、permissions、config schema/values）。"""
    # 事件处理器
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

    # 权限
    permissions: dict | None = None
    try:
        perm_info = s.get_plugin_permissions(meta.name)
        permissions = perm_info.get("permissions")
    except Exception:
        pass

    # 配置
    config_schema = None
    config_values = None
    try:
        config_schema = s.get_plugin_config_schema(meta.name)
        if config_schema and meta.config:
            config_values = meta.config
    except Exception:
        pass

    # UI schema
    ui_schema = None
    if meta.ui_schema_path:
        try:
            import json
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
# 路由 —— 列表 & 详情
# ================================================================== #


@router.post("/install")
async def plugin_install(file: UploadFile = File(...), s: MissevanServer = Depends(get_server)):
    """上传 zip 包安装插件：解压 → 读 metadata → 安装依赖 → 默认启用，返回详情含 README。"""
    if not file.filename or not file.filename.endswith('.zip'):
        raise HTTPException(status_code=400, detail="仅支持 .zip 文件")

    tmp_path = None
    tmp_dir = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name

        # 1. 解压到临时目录，读取 metadata 检测重名
        tmp_dir = tempfile.mkdtemp()
        with zipfile.ZipFile(tmp_path, 'r') as zf:
            zf.extractall(tmp_dir)

        # 查找 metadata.yaml
        plugin_name = None
        for root, _dirs, files in os.walk(tmp_dir):
            for name in ('metadata.yaml', 'metadata.yml'):
                if name in files:
                    with open(os.path.join(root, name), 'r', encoding='utf-8') as f:
                        meta = yaml.safe_load(f) or {}
                        plugin_name = meta.get('name')
                    break
            if plugin_name:
                break

        if not plugin_name:
            raise HTTPException(status_code=400, detail="无法从 zip 中读取有效的 metadata.yaml")

        new_version = meta.get('version', '0.0.0')

        # 2. 检测重名 —— 支持版本更新
        installed = s.plugins
        existing = next((p for p in installed if p.name == plugin_name), None)

        if existing:
            # 比较版本号
            old_ver = _parse_version(existing.version)
            new_ver = _parse_version(new_version)
            if new_ver <= old_ver:
                raise HTTPException(status_code=409,
                    detail=f"插件 '{plugin_name}' v{existing.version} 已安装，上传版本 v{new_version} 不高于现有版本")

            # 仅返回元数据，等待前端确认
            return {
                "action": "update",
                "name": plugin_name,
                "old_version": existing.version,
                "new_version": new_version,
                "enabled": existing.enabled,
            }

        # 3. 执行全新安装
        metadata = await s.install_plugin_from_local(tmp_path)
        try:
            await s._plugin_manager.enable_plugin(metadata.name)
            s._save_state()
        except Exception:
            pass

        readme = ""
        try:
            readme = s.get_plugin_readme(metadata.name) or ""
        except Exception:
            pass

        return {"plugin": _plugin_to_summary(metadata), "readme": readme}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
        if tmp_dir and os.path.exists(tmp_dir):
            shutil.rmtree(tmp_dir, ignore_errors=True)


def _parse_version(v: str) -> tuple:
    """将 '1.2.3' 转为可比较的整数元组。"""
    try:
        return tuple(int(x) for x in str(v).split('.'))
    except Exception:
        return (0,)


@router.post("/install/update")
async def plugin_update(file: UploadFile = File(...), s: MissevanServer = Depends(get_server),
                         was_enabled: bool = Query(default=True)):
    """确认更新插件：停止旧版 → 覆盖目录 → 安装依赖，若之前已启用则自动启用，返回 CHANGELOG。"""
    if not file.filename or not file.filename.endswith('.zip'):
        raise HTTPException(status_code=400, detail="仅支持 .zip 文件")

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name

        # 从 _plugins 中移除旧条目，确保 load_plugin 完整重新加载
        pm = s._plugin_manager
        # 从 zip 中读取插件名
        with zipfile.ZipFile(tmp_path, 'r') as zf:
            meta = {}
            for name in zf.namelist():
                if name.endswith('metadata.yaml') or name.endswith('metadata.yml'):
                    meta = yaml.safe_load(zf.read(name)) or {}
                    break
        plugin_name = meta.get('name', '')
        if plugin_name and plugin_name in pm._plugins:
            # 停用旧实例
            old_meta = pm._plugins[plugin_name]
            if old_meta.enabled:
                try:
                    pm.disable_plugin(plugin_name)
                except Exception:
                    pass
            del pm._plugins[plugin_name]

        metadata = await s.install_plugin_from_local(tmp_path)

        if was_enabled:
            try:
                await pm.enable_plugin(metadata.name)
                s._save_state()
            except Exception:
                pass

        changelog = ""
        try:
            changelog = s.get_plugin_changelog(metadata.name) or ""
        except Exception:
            pass

        return {"plugin": _plugin_to_summary(metadata), "changelog": changelog}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


@router.get("/list", response_model=list[PluginSummary])
async def plugin_list(s: MissevanServer = Depends(get_server)):
    """列出所有已加载插件。"""
    await s._ensure_bot_restored()
    plugins = s.plugins
    return [_plugin_to_summary(p) for p in plugins]


@router.get("/{plugin_name}", response_model=PluginDetailResponse)
async def plugin_info(plugin_name: str, s: MissevanServer = Depends(get_server)):
    """获取插件详情。"""
    pm = s._plugin_manager
    meta = pm.get_plugin(plugin_name)
    if meta is None:
        raise HTTPException(status_code=404, detail=f"插件 '{plugin_name}' 不存在")
    return _plugin_to_detail(s, meta)


@router.get("/{plugin_name}/handlers", response_model=list[PluginEventHandler])
async def plugin_handlers(plugin_name: str, s: MissevanServer = Depends(get_server)):
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
# 路由 —— 启停 & 重载 & 卸载
# ================================================================== #


@router.post("/{plugin_name}/enable", response_model=StatusResponse)
async def plugin_enable(plugin_name: str, s: MissevanServer = Depends(get_server)):
    """启用插件——完成完整加载流程（含异步初始化）。"""
    try:
        await s.enable_plugin(plugin_name)
        return StatusResponse(success=True, message=f"插件 '{plugin_name}' 已启用")
    except CorePluginNotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))
    except CorePluginLoadException as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{plugin_name}/disable", response_model=StatusResponse)
async def plugin_disable(plugin_name: str, s: MissevanServer = Depends(get_server)):
    """禁用插件——从事件总线和命令路由器取消注册。"""
    try:
        await s.disable_plugin(plugin_name)
        s._save_state()
        return StatusResponse(success=True, message=f"插件 '{plugin_name}' 已禁用")
    except CorePluginNotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{plugin_name}/reload", response_model=PluginSummary)
async def plugin_reload(plugin_name: str, s: MissevanServer = Depends(get_server)):
    """重载插件（保留启停状态）。"""
    try:
        pm = s._plugin_manager
        was_enabled = pm.get_plugin(plugin_name).enabled
        # 先卸载旧实例
        pm.suspend_plugin(plugin_name)
        # 强制重新加载模块
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


@router.delete("/{plugin_name}", response_model=StatusResponse)
async def plugin_uninstall(
    plugin_name: str,
    delete_config: bool = Query(default=True),
    delete_data: bool = Query(default=False),
    s: MissevanServer = Depends(get_server),
):
    """卸载插件。"""
    try:
        await s.uninstall_plugin(plugin_name, delete_config=delete_config, delete_data=delete_data)
        return StatusResponse(success=True, message=f"插件 '{plugin_name}' 已卸载")
    except CorePluginNotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))


# ================================================================== #
# 路由 —— 权限
# ================================================================== #


@router.get("/{plugin_name}/permissions", response_model=PluginPermissionInfo)
async def plugin_permissions(plugin_name: str, s: MissevanServer = Depends(get_server)):
    """获取插件的权限配置（含生效状态）。"""
    try:
        info = s.get_plugin_permissions(plugin_name)
        return PluginPermissionInfo(**info)
    except CorePluginNotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/{plugin_name}/permissions", response_model=StatusResponse)
async def plugin_update_permission(
    plugin_name: str,
    req: PluginPermUpdateRequest,
    s: MissevanServer = Depends(get_server),
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
async def plugin_get_config(plugin_name: str, s: MissevanServer = Depends(get_server)):
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
    req: PluginConfigUpdateRequest,
    s: MissevanServer = Depends(get_server),
):
    """更新插件配置。"""
    pm = s._plugin_manager
    meta = pm.get_plugin(plugin_name)
    if meta is None:
        raise HTTPException(status_code=404, detail=f"插件 '{plugin_name}' 不存在")
    try:
        pm.config_manager.save_config(plugin_name, req.config)
        # 同步更新 metadata 中的 config 缓存
        meta.config = req.config
        return StatusResponse(success=True, message=f"配置已保存: {plugin_name}")
    except CorePluginConfigException as e:
        raise HTTPException(status_code=500, detail=str(e))


# ================================================================== #
# 路由 —— README / CHANGELOG
# ================================================================== #


@router.get("/{plugin_name}/readme")
async def plugin_readme(plugin_name: str, s: MissevanServer = Depends(get_server)):
    """获取插件的 README.md 内容。"""
    try:
        content = s.get_plugin_readme(plugin_name)
        return {"content": content or "", "plugin_name": plugin_name}
    except CorePluginNotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{plugin_name}/changelog")
async def plugin_changelog(plugin_name: str, s: MissevanServer = Depends(get_server)):
    """获取插件的 CHANGELOG.md 内容。"""
    try:
        content = s.get_plugin_changelog(plugin_name)
        return {"content": content or "", "plugin_name": plugin_name}
    except CorePluginNotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))


# ================================================================== #
# 路由 —— 失败插件 & 刷新
# ================================================================== #


@router.get("/failed/list", response_model=list[FailedPluginInfo])
async def plugin_failed(s: MissevanServer = Depends(get_server)):
    """列出加载失败的插件。"""
    failed = s.get_failed_plugins()
    return [FailedPluginInfo(**f) for f in failed]


@router.post("/failed/{dir_name}/retry", response_model=PluginSummary)
async def plugin_retry_failed(dir_name: str, s: MissevanServer = Depends(get_server)):
    """重试加载失败的插件。"""
    try:
        meta = await s.retry_failed_plugin(dir_name)
        return _plugin_to_summary(meta)
    except CorePluginNotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/failed/{dir_name}/discard", response_model=StatusResponse)
async def plugin_discard_failed(dir_name: str, s: MissevanServer = Depends(get_server)):
    """放弃加载失败的插件（从列表中移除，保留目录文件）。"""
    try:
        await s.discard_failed_plugin(dir_name)
        return StatusResponse(success=True, message=f"已放弃加载 '{dir_name}'")
    except CorePluginNotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/refresh", response_model=StatusResponse)
async def plugin_refresh(s: MissevanServer = Depends(get_server)):
    """刷新插件目录——扫描并加载新插件。"""
    await s.refresh_plugins()
    return StatusResponse(
        success=True,
        message=f"插件目录已刷新，当前 {len(s.plugins)} 个插件",
    )

"""插件库管理 API 路由(面板级)。

挂载于 ``/api/plugin``。
插件库 = 共享 ``plugins/`` 目录;安装/卸载/刷新在此进行,
各账户从库中启用所需插件(见 ``account_plugins.py``)。
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import shutil
import zipfile
import yaml

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import StreamingResponse

from core.account import AccountManager
from core.exceptions import (
    CorePluginNotFoundException,
    CorePluginLoadException,
)
from api.deps import get_account_manager
from api.schemas import (
    FailedPluginInfo,
    PluginSummary,
    StatusResponse,
)

router = APIRouter()

# 安装互斥锁——同一时间只允许一个安装操作
_install_lock = asyncio.Lock()

_DEP = Depends(get_account_manager)


# ------------------------------------------------------------------ #
# 辅助
# ------------------------------------------------------------------ #

def _parse_version(v: str) -> tuple:
    """将 '1.2.3' 转为可比较的整数元组。"""
    try:
        return tuple(int(x) for x in str(v).split('.'))
    except Exception:
        return (0,)


def _read_plugin_name_from_zip(path: str) -> str:
    """从 zip 中读取插件名。"""
    with zipfile.ZipFile(path, 'r') as zf:
        for name in zf.namelist():
            if name.endswith('metadata.yaml') or name.endswith('metadata.yml'):
                return str((yaml.safe_load(zf.read(name)) or {}).get('name', ''))
    return ''


def _find_plugin_name_in_dir(d: str) -> str | None:
    """在解压目录中查找 metadata 并返回插件名。"""
    for root, _dirs, files in os.walk(d):
        for fname in ('metadata.yaml', 'metadata.yml'):
            if fname in files:
                with open(os.path.join(root, fname), 'r', encoding='utf-8') as f:
                    meta = yaml.safe_load(f) or {}
                    return str(meta.get('name')) or None
    return None


# ================================================================== #
# 路由 —— 安装(库级)
# ================================================================== #


async def _install_stream(file: UploadFile, manager: AccountManager):
    """SSE 流式安装——逐步骤推送日志到前端。"""
    async def send(msg: str, done: bool = False):
        data = json.dumps({"message": msg, "done": done}, ensure_ascii=False)
        yield f"data: {data}\n\n"

    if not file.filename or not file.filename.endswith('.zip'):
        async for chunk in send("错误：仅支持 .zip 文件", True):
            yield chunk
        return

    async for chunk in send(f"开始安装 {file.filename} ..."):
        yield chunk

    tmp_path = None
    tmp_dir = None
    try:
        async for chunk in send("正在保存上传文件 ..."):
            yield chunk
        with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name

        async for chunk in send("正在解压并读取元数据 ..."):
            yield chunk
        tmp_dir = tempfile.mkdtemp()
        with zipfile.ZipFile(tmp_path, 'r') as zf:
            zf.extractall(tmp_dir)
        plugin_name = _find_plugin_name_in_dir(tmp_dir)
        if not plugin_name:
            async for chunk in send("错误：无法从 zip 中读取有效的 metadata.yaml", True):
                yield chunk
            return

        async for chunk in send(f"正在安装插件: {plugin_name} ..."):
            yield chunk
        pm = manager.get_library_pm()
        metadata = await pm.install_plugin(local_path=tmp_path)
        await manager.refresh_library()
        async for chunk in send(f"插件 {plugin_name} 已加入插件库（可在账户中启用）", True):
            yield chunk
    except Exception as e:
        async for chunk in send(f"错误: {e}", True):
            yield chunk
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
        if tmp_dir and os.path.exists(tmp_dir):
            shutil.rmtree(tmp_dir, ignore_errors=True)


@router.post("/install/stream")
async def plugin_install_stream(
    file: UploadFile = File(...), manager: AccountManager = _DEP
):
    """流式安装插件（SSE），前端实时显示进度日志。"""
    if _install_lock.locked():
        raise HTTPException(status_code=409, detail="另一个插件安装正在进行中，请稍候")
    async with _install_lock:
        return StreamingResponse(
            _install_stream(file, manager),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )


@router.post("/install")
async def plugin_install(
    file: UploadFile = File(...), manager: AccountManager = _DEP
):
    """上传 zip 包安装到插件库（不自动启用，由各账户自行启用）。"""
    if not file.filename or not file.filename.endswith('.zip'):
        raise HTTPException(status_code=400, detail="仅支持 .zip 文件")

    tmp_path = None
    tmp_dir = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name

        tmp_dir = tempfile.mkdtemp()
        with zipfile.ZipFile(tmp_path, 'r') as zf:
            zf.extractall(tmp_dir)

        plugin_name = _find_plugin_name_in_dir(tmp_dir)
        if not plugin_name:
            raise HTTPException(status_code=400, detail="无法从 zip 中读取有效的 metadata.yaml")

        pm = manager.get_library_pm()
        existing = pm.get_plugin(plugin_name)
        if existing:
            old_ver = _parse_version(existing.version)
            new_meta_path = os.path.join(tmp_dir, "metadata.yaml")
            with open(new_meta_path, "r", encoding="utf-8") as f:
                meta = yaml.safe_load(f) or {}
            new_ver = _parse_version(meta.get("version", "0.0.0"))
            if new_ver <= old_ver:
                raise HTTPException(status_code=409,
                    detail=f"插件 '{plugin_name}' v{existing.version} 已安装，上传版本不高于现有版本")
            return {
                "action": "update",
                "name": plugin_name,
                "old_version": existing.version,
                "new_version": meta.get("version"),
                "enabled": False,
            }

        metadata = await pm.install_plugin(local_path=tmp_path)
        await manager.refresh_library()
        return {"plugin": metadata.name, "readme": ""}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
        if tmp_dir and os.path.exists(tmp_dir):
            shutil.rmtree(tmp_dir, ignore_errors=True)


@router.post("/install/update")
async def plugin_update(
    file: UploadFile = File(...), manager: AccountManager = _DEP,
    was_enabled: bool = Query(default=True),
):
    """确认更新插件：覆盖库目录并安装依赖，各账户实例由启用状态决定。"""
    if not file.filename or not file.filename.endswith('.zip'):
        raise HTTPException(status_code=400, detail="仅支持 .zip 文件")

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name

        pm = manager.get_library_pm()
        plugin_name = _read_plugin_name_from_zip(tmp_path)
        if not plugin_name:
            raise HTTPException(status_code=400, detail="无法从 zip 中读取有效的 metadata.yaml")

        # 从库中移除旧条目,确保 install_plugin 完整重新加载新版本
        if plugin_name in pm._plugins:
            del pm._plugins[plugin_name]
        await pm.install_plugin(local_path=tmp_path)
        await manager.refresh_library()
        # 各账户中已启用的实例重载为新版本
        await manager.reload_plugin_in_accounts(plugin_name)
        return {"plugin": plugin_name, "changelog": ""}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


# ================================================================== #
# 路由 —— 库列表 & 文档
# ================================================================== #


@router.get("/list")
async def plugin_list(manager: AccountManager = _DEP):
    """插件库列表(含被哪些账户启用)。"""
    return manager.list_library_plugins()


@router.get("/{plugin_name}/readme")
async def plugin_readme(plugin_name: str, manager: AccountManager = _DEP):
    """获取插件 README.md 内容。"""
    try:
        content = manager.get_library_pm().get_plugin_readme(plugin_name)
        return {"content": content or "", "plugin_name": plugin_name}
    except CorePluginNotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{plugin_name}/changelog")
async def plugin_changelog(plugin_name: str, manager: AccountManager = _DEP):
    """获取插件 CHANGELOG.md 内容。"""
    try:
        content = manager.get_library_pm().get_plugin_changelog(plugin_name)
        return {"content": content or "", "plugin_name": plugin_name}
    except CorePluginNotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))


# ================================================================== #
# 路由 —— 卸载 / 失败插件 / 刷新
# ================================================================== #


@router.delete("/{plugin_name}", response_model=StatusResponse)
async def plugin_uninstall(
    plugin_name: str,
    delete_config: bool = Query(default=True),
    delete_data: bool = Query(default=False),
    manager: AccountManager = _DEP,
):
    """卸载插件:级联禁用各账户实例,可选清除各账户配置/数据,再从库删除。"""
    try:
        await manager.uninstall_plugin(plugin_name, delete_config=delete_config, delete_data=delete_data)
        return StatusResponse(success=True, message=f"插件 '{plugin_name}' 已从插件库卸载")
    except CorePluginNotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/failed/list", response_model=list[FailedPluginInfo])
async def plugin_failed(manager: AccountManager = _DEP):
    """列出加载失败的插件。"""
    failed = manager.get_library_pm().get_failed_plugins()
    return [FailedPluginInfo(**f) for f in failed]


@router.post("/failed/{dir_name}/retry", response_model=PluginSummary)
async def plugin_retry_failed(dir_name: str, manager: AccountManager = _DEP):
    """重试加载失败的插件。"""
    try:
        pm = manager.get_library_pm()
        meta = await pm.retry_failed_plugin(dir_name)
        await manager.refresh_library()
        return PluginSummary(
            name=meta.name, plugin_id=meta.plugin_id, author=meta.author,
            version=meta.version, display_name=meta.display_name,
            short_desc=meta.short_desc, desc=meta.desc, enabled=False,
            has_config=meta.config_schema_path is not None,
            has_readme=meta.readme_path is not None,
            has_ui=meta.ui_schema_path is not None,
            has_changelog=False,
        )
    except CorePluginNotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/failed/{dir_name}/discard", response_model=StatusResponse)
async def plugin_discard_failed(dir_name: str, manager: AccountManager = _DEP):
    """放弃加载失败的插件（从列表中移除，保留目录文件）。"""
    try:
        manager.get_library_pm().discard_failed_plugin(dir_name)
        return StatusResponse(success=True, message=f"已放弃加载 '{dir_name}'")
    except CorePluginNotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/refresh", response_model=StatusResponse)
async def plugin_refresh(manager: AccountManager = _DEP):
    """刷新插件库目录——扫描并加载新插件(同步各账户)。"""
    await manager.refresh_library()
    return StatusResponse(
        success=True,
        message=f"插件库已刷新，当前 {len(manager.list_library_plugins())} 个插件",
    )

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


def _read_plugin_meta_from_zip(path: str) -> dict:
    """从 zip 中读取插件元数据（取第一个 metadata.yaml / yml 成员）。

    插件元数据可能位于归档的子目录中，故按成员名后缀匹配而非固定路径。
    """
    with zipfile.ZipFile(path, 'r') as zf:
        for name in zf.namelist():
            if name.endswith('metadata.yaml') or name.endswith('metadata.yml'):
                return yaml.safe_load(zf.read(name)) or {}
    return {}


def _safe_member_path(name: str) -> str | None:
    """校验 zip 成员名,返回可安全落盘的相对路径;非法成员返回 None。

    拒绝绝对路径、``..`` 路径段与 Windows 盘符,防止 Zip Slip。
    与 ``update.py:_safe_rel`` 同源——该文件属于在线更新链路,
    此处保留独立实现以免两处互相牵动。
    """
    rel = name.replace("\\", "/")
    if not rel or rel.startswith("/") or rel.startswith("../"):
        return None
    parts = [p for p in rel.split("/") if p not in ("", ".")]
    if not parts or any(p == ".." for p in parts):
        return None
    # Windows 盘符前缀(C:/ 或 C:foo)——在 Windows 上会被当作绝对路径
    if len(parts[0]) >= 2 and parts[0][1] == ":":
        return None
    return "/".join(parts)


def _safe_extract_zip(zip_path: str, dest: str) -> None:
    """解压 zip 到 dest,逐成员校验路径后写出。

    不使用 ``ZipFile.extractall``——它会直接采用归档内的成员名,
    含 ``../`` 或绝对路径的成员可写出 dest 之外(Zip Slip)。
    非法成员静默跳过。
    """
    with zipfile.ZipFile(zip_path, "r") as zf:
        for info in zf.infolist():
            rel = _safe_member_path(info.filename)
            if rel is None:
                continue
            target = os.path.join(dest, *rel.split("/"))
            if info.is_dir():
                os.makedirs(target, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)


def _find_metadata_file(d: str) -> str | None:
    """在解压目录中递归查找 metadata 文件,返回其完整路径。"""
    for root, _dirs, files in os.walk(d):
        for fname in ('metadata.yaml', 'metadata.yml'):
            if fname in files:
                return os.path.join(root, fname)
    return None


def _find_plugin_name_in_dir(d: str) -> str | None:
    """在解压目录中查找 metadata 并返回插件名(缺失或非法返回 None)。"""
    meta_path = _find_metadata_file(d)
    if meta_path is None:
        return None
    with open(meta_path, 'r', encoding='utf-8') as f:
        meta = yaml.safe_load(f) or {}
    name = meta.get('name')
    if not name:
        return None
    return str(name)


# ================================================================== #
# 路由 —— 安装(库级)
# ================================================================== #


async def _install_stream(file: UploadFile, manager: AccountManager):
    """SSE 流式安装——逐步骤推送日志到前端。

    互斥锁在生成器内部获取:若在 ``plugin_install_stream`` 返回
    ``StreamingResponse`` 之前获取,``async with`` 会在响应体开始消费前
    就退出,锁形同虚设。
    """
    async with _install_lock:
        async for chunk in _install_stream_locked(file, manager):
            yield chunk


async def _install_stream_locked(file: UploadFile, manager: AccountManager):
    """``_install_stream`` 的实际实现——调用方须已持有 ``_install_lock``。"""
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
        await asyncio.to_thread(_safe_extract_zip, tmp_path, tmp_dir)
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
    # 快速失败:让并发请求拿到 409 而不是排队;真正的互斥由
    # _install_stream 生成器内部持有的锁保证。
    if _install_lock.locked():
        raise HTTPException(status_code=409, detail="另一个插件安装正在进行中，请稍候")
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
        await asyncio.to_thread(_safe_extract_zip, tmp_path, tmp_dir)

        plugin_name = _find_plugin_name_in_dir(tmp_dir)
        if not plugin_name:
            raise HTTPException(status_code=400, detail="无法从 zip 中读取有效的 metadata.yaml")

        pm = manager.get_library_pm()
        existing = pm.get_plugin(plugin_name)
        if existing:
            old_ver = _parse_version(existing.version)
            # 元数据可能位于解压目录的子目录中(_find_plugin_name_in_dir 递归查找),
            # 不能按固定的根路径读取。
            meta_path = _find_metadata_file(tmp_dir)
            meta: dict = {}
            if meta_path:
                with open(meta_path, "r", encoding="utf-8") as f:
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

        async with _install_lock:
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
        meta = _read_plugin_meta_from_zip(tmp_path)
        plugin_name = str(meta.get('name', ''))
        if not plugin_name:
            raise HTTPException(status_code=400, detail="无法从 zip 中读取有效的 metadata.yaml")

        async with _install_lock:
            # 与 /install 保持同一套版本规则:不允许用不高于现有版本的包覆盖,
            # 否则本端点会成为绕过 /install 版本校验的降级通道
            existing = pm.get_plugin(plugin_name)
            if existing is not None:
                new_ver = _parse_version(meta.get("version", "0.0.0"))
                if new_ver <= _parse_version(existing.version):
                    raise HTTPException(
                        status_code=409,
                        detail=f"插件 '{plugin_name}' v{existing.version} 已安装，"
                               f"上传版本不高于现有版本，无法覆盖",
                    )
            # 从库中移除旧条目,确保 install_plugin 完整重新加载新版本
            if plugin_name in pm._plugins:
                del pm._plugins[plugin_name]
            await pm.install_plugin(local_path=tmp_path)
            await manager.refresh_library()
            # 各账户中已启用的实例重载为新版本
            await manager.reload_plugin_in_accounts(plugin_name)
        return {"plugin": plugin_name, "changelog": ""}
    except HTTPException:
        raise  # 版本冲突等已带明确状态码，勿被兜底吞成 500
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
    delete_data: bool = Query(default=True),
    disable_in_accounts: bool = Query(default=False),
    manager: AccountManager = _DEP,
):
    """卸载插件:彻底删除库源文件;可选停用各账户中已启用的实例(副本保留)。"""
    try:
        await manager.uninstall_plugin(
            plugin_name,
            delete_config=delete_config,
            delete_data=delete_data,
            disable_in_accounts=disable_in_accounts,
        )
        return StatusResponse(success=True, message=f"插件 '{plugin_name}' 已从插件库删除")
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
            has_changelog=meta.changelog_path is not None,
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


# ================================================================== #
# 路由 —— 批量推送到账户
# ================================================================== #


def _push_summary(result: dict) -> str:
    """把推送结果拼成一句可直接展示的话。"""
    msg = f"已更新 {len(result['updated'])} 项，跳过 {len(result['skipped'])} 项"
    if result["failed"]:
        msg += f"，失败 {len(result['failed'])} 项"
    return msg


@router.post("/{plugin_name}/push")
async def plugin_push_to_accounts(plugin_name: str, manager: AccountManager = _DEP):
    """把该插件的库版本推送到各账户副本。

    只处理**已安装该插件**的账户，并跳过副本版本不低于库版本的
    （更新会 stop/start 插件实例，断掉插件消息与内部状态，无谓重载应当避免）。
    因此手动改过副本的账户、以及已是最新的账户都不会被触碰。
    """
    try:
        result = await manager.push_plugin_to_accounts(plugin_name)
    except CorePluginNotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {**result, "message": _push_summary(result)}


@router.post("/push-all")
async def plugin_push_all(manager: AccountManager = _DEP):
    """把插件库中全部插件推送到各账户副本（版本守卫同单个推送）。"""
    result = await manager.push_plugin_to_accounts(None)
    return {**result, "message": _push_summary(result)}


# ================================================================== #
# 路由 —— 默认插件
# ================================================================== #


@router.post("/{plugin_name}/default")
async def plugin_set_default(
    plugin_name: str, body: dict, manager: AccountManager = _DEP
):
    """把插件设为 / 取消「默认插件」。

    默认插件在**新建账户**时自动安装并启用；存量账户需调用
    ``POST /api/plugin/apply-defaults`` 显式补齐。
    """
    if manager.get_library_pm().get_plugin(plugin_name) is None:
        raise HTTPException(status_code=404, detail=f"插件 '{plugin_name}' 不在插件库中")
    defaults = manager.set_plugin_default(plugin_name, bool(body.get("default", True)))
    return {"success": True, "default_plugins": defaults}


@router.post("/apply-defaults")
async def plugin_apply_defaults(manager: AccountManager = _DEP):
    """把默认插件补齐到全部现有账户（已装则跳过，未启用则启用）。"""
    result = await manager.apply_default_plugins()
    accounts = len(result["applied"])
    msg = f"已为 {accounts} 个账户补齐默认插件" if accounts else "所有账户均无需补齐"
    if result["failed"]:
        msg += f"；清单中不存在于库: {', '.join(result['failed'])}"
    return {**result, "message": msg}

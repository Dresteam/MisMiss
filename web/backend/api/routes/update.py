"""程序更新 API。

以 GitHub Releases 为更新源，支持：
- 版本历史与更新日志查看
- 新版本检测
- 执行更新
- 回滚到上一版本
- 镜像站 / 代理配置
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from core import MissevanServer
from core.config import ServerConfig
from api.deps import get_server
from api.schemas import StatusResponse

router = APIRouter()

_GITHUB_REPO = "Dresteam/MisMiss"
_GITHUB_API = "https://api.github.com"
_UPDATE_STATE_FILE = Path("data/update_state.json")

# 版本号（运行时从 pyproject.toml 或环境变量读取）
try:
    _CURRENT_VERSION = os.environ.get("MISMISS_VERSION", "1.0.0-beta.3")
except Exception:
    _CURRENT_VERSION = "0.0.0"


# ------------------------------------------------------------------ #
# 配置读取
# ------------------------------------------------------------------ #

def _update_config() -> dict:
    """读取 update 配置（含镜像/代理）。"""
    cfg = ServerConfig.load()
    return {
        "repo": cfg.get_str("update.repo", _GITHUB_REPO),
        "mirror": cfg.get_str("update.mirror", ""),
        "proxy": cfg.get_str("update.proxy", ""),
    }


def _save_update_config(repo: str, mirror: str, proxy: str) -> None:
    """保存 update 配置到 config.yml。"""
    import yaml
    config_path = Path(__file__).resolve().parent.parent.parent.parent.parent / "config.yml"
    data: dict = {}
    if config_path.exists():
        try:
            data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        except Exception:
            data = {}
    data.setdefault("update", {})
    data["update"]["repo"] = repo
    data["update"]["mirror"] = mirror
    data["update"]["proxy"] = proxy
    config_path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")


def _load_update_state() -> dict:
    """加载更新状态（备份信息）。"""
    if _UPDATE_STATE_FILE.exists():
        try:
            return json.loads(_UPDATE_STATE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_update_state(state: dict) -> None:
    _UPDATE_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _UPDATE_STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ------------------------------------------------------------------ #
# GitHub API 访问
# ------------------------------------------------------------------ #

def _github_request(path: str) -> dict:
    """请求 GitHub API（支持镜像与代理）。"""
    cfg = _update_config()
    api_base = cfg["mirror"].rstrip("/") if cfg["mirror"] else _GITHUB_API
    url = f"{api_base}{path}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "MisMiss-Updater/1.0",
            "Accept": "application/vnd.github+json",
        },
    )
    opener = urllib.request.build_opener()
    if cfg["proxy"]:
        proxy_handler = urllib.request.ProxyHandler({
            "http": cfg["proxy"],
            "https": cfg["proxy"],
        })
        opener = urllib.request.build_opener(proxy_handler)
    try:
        with opener.open(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"GitHub API 请求失败: {e}")


# ================================================================== #
# 路由
# ================================================================== #


@router.get("/info")
async def update_info():
    """当前版本与更新配置。"""
    cfg = _update_config()
    state = _load_update_state()
    return {
        "current_version": _CURRENT_VERSION,
        "repo": cfg["repo"],
        "mirror": cfg["mirror"],
        "proxy": cfg["proxy"],
        "has_backup": bool(state.get("backup_dir")),
        "backup_version": state.get("backup_version", ""),
    }


@router.get("/check")
async def update_check():
    """检测最新版本。"""
    cfg = _update_config()
    releases = _github_request(f"/repos/{cfg['repo']}/releases")
    if not releases:
        return {"latest": None, "up_to_date": True, "releases": []}
    latest = releases[0]
    latest_tag = latest.get("tag_name", "").lstrip("v")
    return {
        "latest": latest_tag,
        "latest_name": latest.get("name", latest_tag),
        "up_to_date": latest_tag == _CURRENT_VERSION,
        "body": latest.get("body", ""),
        "releases": [
            {
                "tag": r.get("tag_name", "").lstrip("v"),
                "name": r.get("name", ""),
                "published_at": r.get("published_at", ""),
                "body": r.get("body", ""),
                "assets": [
                    {"name": a.get("name", ""), "url": a.get("browser_download_url", "")}
                    for a in r.get("assets", [])
                ],
            }
            for r in releases[:20]
        ],
    }


@router.get("/changelog/{version}")
async def update_changelog(version: str):
    """获取指定版本的更新日志。"""
    cfg = _update_config()
    releases = _github_request(f"/repos/{cfg['repo']}/releases")
    for r in releases:
        tag = r.get("tag_name", "").lstrip("v")
        if tag == version:
            return {"version": tag, "name": r.get("name", ""), "body": r.get("body", "")}
    raise HTTPException(status_code=404, detail=f"版本 {version} 不存在")


@router.post("/settings", response_model=StatusResponse)
async def update_settings(body: dict, s: MissevanServer = Depends(get_server)):
    """保存更新配置（镜像站 / 代理）。"""
    repo = str(body.get("repo", _GITHUB_REPO)).strip() or _GITHUB_REPO
    mirror = str(body.get("mirror", "")).strip()
    proxy = str(body.get("proxy", "")).strip()
    _save_update_config(repo, mirror, proxy)
    return StatusResponse(success=True, message="更新配置已保存")


@router.post("/apply", response_model=StatusResponse)
async def update_apply(body: dict, s: MissevanServer = Depends(get_server)):
    """执行更新到指定版本。

    请求体：``{"version": "1.0.0-beta.4", "asset_name": "mismiss.zip"}``
    """
    cfg = _update_config()
    target_version = str(body.get("version", "")).strip()
    if not target_version:
        raise HTTPException(status_code=400, detail="必须指定目标版本")

    releases = _github_request(f"/repos/{cfg['repo']}/releases")
    target = None
    for r in releases:
        if r.get("tag_name", "").lstrip("v") == target_version:
            target = r
            break
    if target is None:
        raise HTTPException(status_code=404, detail=f"版本 {target_version} 不存在")

    assets = target.get("assets", [])
    asset_name = str(body.get("asset_name", "")).strip()
    asset_url = None
    if asset_name:
        for a in assets:
            if a.get("name") == asset_name:
                asset_url = a.get("browser_download_url")
                break
        if not asset_url:
            raise HTTPException(status_code=404, detail=f"资源 {asset_name} 不存在")
    else:
        # 默认取第一个 zip 资产
        for a in assets:
            if a.get("name", "").endswith((".zip", ".tar.gz")):
                asset_url = a.get("browser_download_url")
                asset_name = a.get("name", "")
                break
        if not asset_url:
            raise HTTPException(status_code=400, detail="该版本没有可下载的更新包")

    # 备份当前版本
    project_root = Path(__file__).resolve().parent.parent.parent.parent.parent
    backup_dir = project_root / "data" / "backup" / f"v{_CURRENT_VERSION}"
    try:
        if backup_dir.exists():
            shutil.rmtree(backup_dir)
        backup_dir.parent.mkdir(parents=True, exist_ok=True)
        for item in ["src", "web", "plugins", "scripts", "config.yml"]:
            src = project_root / item
            if src.exists():
                dst = backup_dir / item
                if src.is_dir():
                    shutil.copytree(src, dst)
                else:
                    shutil.copy2(src, dst)
        _save_update_state({"backup_dir": str(backup_dir), "backup_version": _CURRENT_VERSION})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"备份失败: {e}")

    # 下载更新包
    try:
        tmp_zip = project_root / "data" / f"update_{target_version}.zip"
        req = urllib.request.Request(asset_url, headers={"User-Agent": "MisMiss-Updater/1.0"})
        opener = urllib.request.build_opener()
        if cfg["proxy"]:
            proxy_handler = urllib.request.ProxyHandler({"http": cfg["proxy"], "https": cfg["proxy"]})
            opener = urllib.request.build_opener(proxy_handler)
        with opener.open(req, timeout=300) as resp, open(tmp_zip, "wb") as f:
            f.write(resp.read())

        # 解压覆盖
        import zipfile
        with zipfile.ZipFile(tmp_zip) as zf:
            zf.extractall(project_root)
        tmp_zip.unlink(missing_ok=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新包下载/解压失败: {e}")

    return StatusResponse(
        success=True,
        message=f"已更新到 v{target_version}，服务即将重启",
    )


@router.post("/rollback", response_model=StatusResponse)
async def update_rollback(s: MissevanServer = Depends(get_server)):
    """回滚到上一版本。"""
    state = _load_update_state()
    backup_dir = state.get("backup_dir", "")
    if not backup_dir or not Path(backup_dir).exists():
        raise HTTPException(status_code=400, detail="没有可用的备份，无法回滚")

    project_root = Path(__file__).resolve().parent.parent.parent.parent.parent
    try:
        for item in ["src", "web", "plugins", "scripts", "config.yml"]:
            src = Path(backup_dir) / item
            dst = project_root / item
            if not src.exists():
                continue
            if dst.exists():
                if dst.is_dir():
                    shutil.rmtree(dst)
                else:
                    dst.unlink()
            if src.is_dir():
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"回滚失败: {e}")

    # 清除备份状态
    _save_update_state({})
    return StatusResponse(
        success=True,
        message=f"已回滚到 v{state.get('backup_version', '?')}，服务即将重启",
    )

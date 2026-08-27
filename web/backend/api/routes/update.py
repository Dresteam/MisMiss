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
import re
import shutil
import subprocess
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

# 是否运行在 Docker 容器内（Docker 会在容器根目录创建 /.dockerenv）
_IS_DOCKER = Path("/.dockerenv").exists()
# docker.sock 是否挂载（在线更新需要）
_DOCKER_SOCKET = Path("/var/run/docker.sock").exists()
# 宿主部署目录（compose 挂载到 /app/deploy）——在线更新在此下载/解压部署包
_DEPLOY_DIR = Path("/app/deploy")
_BACKUP_DIR = _DEPLOY_DIR / ".mismiss-backup"
_UPDATE_TMP_DIR = _DEPLOY_DIR / ".mismiss-update"

_DOCKER_UPDATE_HINT = (
    "未挂载 docker.sock / 部署目录，在线更新不可用。"
    "请通过部署包手动更新（bash deploy.sh）。"
)

# 版本号（运行时从 pyproject.toml 或环境变量读取）
try:
    _CURRENT_VERSION = os.environ.get("MISMISS_VERSION", "1.0.0")
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
    """保存 update 配置到 config.yml（原子写入，避免与其他写入并发时损坏）。"""
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
    tmp_path = config_path.with_suffix(config_path.suffix + ".tmp")
    tmp_path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    os.replace(tmp_path, config_path)


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

def _mirror_base(cfg: dict) -> str:
    """解析镜像配置，返回统一的前缀（不含尾部斜杠）。

    兼容两种格式：
    - 前缀代理（新格式）：``https://gh-proxy.com/``
      → API 与下载地址统一加此前缀
    - 完整 API 地址（旧格式）：``https://ghproxy.com/https://api.github.com``
      → 仅加速 API，自动提取前缀用于下载
    """
    mirror = (cfg.get("mirror") or "").strip().rstrip("/")
    if not mirror:
        return ""
    if mirror.endswith("https://api.github.com"):
        return mirror[: -len("https://api.github.com")].rstrip("/")
    return mirror


_VERSION_RE = re.compile(
    r"^(\d+)\.(\d+)\.(\d+)(?:-(alpha|beta|rc|a|b|c)\.?(\d+))?", re.IGNORECASE
)
"""版本号解析：``1.0.0`` / ``1.0.0-beta.3``（v 前缀自动忽略）。"""


def _parse_version(tag: str) -> tuple[int, int, int, int, int, int] | None:
    """解析版本号为可比较元组，失败返回 ``None``。

    元组为 ``(major, minor, patch, is_final, pre_rank, pre_num)``：
    ``is_final`` 为 1 表示正式版（高于任何预发布版）；
    预发布按 alpha < beta < rc 排序。
    """
    m = _VERSION_RE.match(tag.strip().lstrip("v"))
    if not m:
        return None
    major, minor, patch = int(m.group(1)), int(m.group(2)), int(m.group(3))
    pre = m.group(4)
    if not pre:
        return (major, minor, patch, 1, 0, 0)
    rank = {"alpha": 0, "a": 0, "beta": 1, "b": 1, "rc": 2, "c": 2}[pre.lower()]
    num = int(m.group(5) or 0)
    return (major, minor, patch, 0, rank, num)


def _github_request(path: str) -> dict:
    """请求 GitHub API（支持镜像与代理）。"""
    cfg = _update_config()
    prefix = _mirror_base(cfg)
    api_base = f"{prefix}/{_GITHUB_API}" if prefix else _GITHUB_API
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


# ------------------------------------------------------------------ #
# 更新包解压（zip / tar.gz，剥离顶层目录）
# ------------------------------------------------------------------ #

# 覆盖时跳过的根级文件 —— config.yml 为用户配置，不能被更新包模板覆盖
_SKIP_OVERWRITE = {"config.yml"}


def _normalize(name: str) -> str:
    """归一化归档成员路径（Windows zip 使用反斜杠）。"""
    return name.replace("\\", "/").rstrip("/")


def _top_dir(names: list[str]) -> str:
    """返回归档成员公共顶层目录（如 ``mismiss-1.0.0/``），扁平归档返回空串。"""
    normalized = [n for n in (_normalize(x) for x in names) if n]
    if not normalized:
        return ""
    first = normalized[0]
    if "/" not in first:
        return ""  # 扁平归档，无顶层目录
    head = first.split("/")[0]
    for n in normalized:
        if n != head and not n.startswith(head + "/"):
            return ""
    return head


def _safe_rel(name: str, top: str) -> str:
    """计算剥离顶层后的相对路径；非法（路径穿越 / 顶层目录自身）返回空串。"""
    rel = _normalize(name)
    if top:
        if rel == top:
            return ""
        if not rel.startswith(top + "/"):
            return ""
        rel = rel[len(top) + 1:]
    if not rel or rel.startswith(("/", "../")) or ".." in rel.split("/"):
        return ""
    return rel


def _extract_archive(archive_path: Path, dest: Path, skip: set[str] | None = None) -> None:
    """解压源码归档到 dest：剥离顶层目录、防路径穿越、跳过指定根级文件。"""
    import tarfile
    import zipfile

    skip = skip or _SKIP_OVERWRITE

    if archive_path.name.endswith(".tar.gz"):
        with tarfile.open(archive_path, "r:gz") as tf:
            members = tf.getmembers()
            top = _top_dir([m.name for m in members])
            for m in members:
                rel = _safe_rel(m.name, top)
                if not rel or rel in skip:
                    continue
                if m.isdir():
                    (dest / rel).mkdir(parents=True, exist_ok=True)
                    continue
                src = tf.extractfile(m)
                if src is None:  # 符号链接等特殊成员
                    continue
                (dest / rel).parent.mkdir(parents=True, exist_ok=True)
                with open(dest / rel, "wb") as out:
                    shutil.copyfileobj(src, out)
    else:
        with zipfile.ZipFile(archive_path) as zf:
            names = zf.namelist()
            top = _top_dir(names)
            for name in names:
                rel = _safe_rel(name, top)
                if not rel or rel in skip:
                    continue
                if name.endswith(("/", "\\")):  # 目录成员
                    (dest / rel).mkdir(parents=True, exist_ok=True)
                    continue
                (dest / rel).parent.mkdir(parents=True, exist_ok=True)
                with zf.open(name) as src, open(dest / rel, "wb") as out:
                    shutil.copyfileobj(src, out)


# ------------------------------------------------------------------ #
# Docker 在线更新（通过 docker.sock 操作宿主 Docker）
# ------------------------------------------------------------------ #

_docker_access_probed = False
_docker_access_ok = False


def _docker_ready() -> bool:
    """在线更新可用：容器内可访问 docker.sock 且部署目录已挂载。

    除静态检查外，首次调用时实际探测一次 socket 访问权限
    （如 Docker Desktop 的 socket gid=0 场景，mismiss 用户实际不可访问）。
    """
    global _docker_access_probed, _docker_access_ok
    if not (_IS_DOCKER and _DOCKER_SOCKET and _DEPLOY_DIR.is_dir()):
        return False
    if not _docker_access_probed:
        _docker_access_probed = True
        try:
            _docker_access_ok = (
                subprocess.run(["docker", "info"], capture_output=True, timeout=10).returncode == 0
            )
        except Exception:
            _docker_access_ok = False
    return _docker_access_ok


def _run(cmd: list[str], timeout: int = 120) -> str:
    """执行 docker CLI 命令；失败抛 HTTPException（附 stderr 摘要）。"""
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail=f"命令不存在: {cmd[0]}")
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=500, detail=f"命令超时: {' '.join(cmd[:3])} ...")
    if proc.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail=f"命令失败: {' '.join(cmd[:3])} ...\n{proc.stderr.strip()[-500:]}",
        )
    return proc.stdout


def _deploy_home() -> str:
    """读取部署目录 .env 中的 MISMISS_HOME（宿主绝对路径）。"""
    env_file = _DEPLOY_DIR / ".env"
    if not env_file.exists():
        raise HTTPException(
            status_code=400,
            detail="部署目录缺少 .env（MISMISS_HOME 未注入）。请用最新版 deploy.sh 重新部署一次后重试。",
        )
    for line in env_file.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("MISMISS_HOME="):
            home = line.split("=", 1)[1].strip().strip('"').strip("'")
            if home:
                return home
    raise HTTPException(
        status_code=400,
        detail="部署目录 .env 缺少 MISMISS_HOME。请用最新版 deploy.sh 重新部署一次后重试。",
    )


def _docker_select_asset(assets: list[dict], version: str) -> tuple[str, str]:
    """选择 Docker 部署包资产，返回 (下载地址, 文件名)。"""
    preferred = (f"mismiss-{version}-docker.zip", f"mismiss-{version}-docker.tar.gz")
    for a in assets:
        if a.get("name") in preferred:
            return a.get("browser_download_url", ""), a.get("name", "")
    for a in assets:
        name = a.get("name", "")
        if "-docker" in name and name.endswith((".zip", ".tar.gz")):
            return a.get("browser_download_url", ""), name
    raise HTTPException(
        status_code=400,
        detail=f"版本 {version} 没有 Docker 部署包资产（mismiss-<版本>-docker.zip / .tar.gz）",
    )


def _download_asset(asset_url: str, dest: Path, cfg: dict) -> None:
    """下载更新包（配置了镜像时下载地址也走前缀代理）。"""
    prefix = _mirror_base(cfg)
    if prefix:
        asset_url = f"{prefix}/{asset_url}"
    try:
        req = urllib.request.Request(asset_url, headers={"User-Agent": "MisMiss-Updater/1.0"})
        opener = urllib.request.build_opener()
        if cfg["proxy"]:
            proxy_handler = urllib.request.ProxyHandler({"http": cfg["proxy"], "https": cfg["proxy"]})
            opener = urllib.request.build_opener(proxy_handler)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with opener.open(req, timeout=300) as resp, open(dest, "wb") as f:
            f.write(resp.read())
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新包下载失败: {e}")


def _verify_docker_package(pkg_path: Path) -> None:
    """校验 Docker 部署包：含 docker-compose.yml 与 mismiss-docker.tar.gz，
    且内层镜像归档是标准 docker save 格式（根含 manifest.json）。"""
    import io
    import tarfile
    import zipfile

    names: list[str] = []
    image_reader = None
    if pkg_path.name.endswith(".tar.gz"):
        tf = tarfile.open(pkg_path, "r:gz")
        names = [_normalize(n) for n in tf.getnames()]
        for m in tf.getmembers():
            if m.isfile() and _normalize(m.name).endswith("mismiss-docker.tar.gz"):
                image_reader = tf.extractfile(m)
                break
    else:
        zf = zipfile.ZipFile(pkg_path)
        names = [_normalize(n) for n in zf.namelist()]
        for n in zf.namelist():
            if _normalize(n).endswith("mismiss-docker.tar.gz"):
                image_reader = io.BytesIO(zf.read(n))
                break

    if not any(n.endswith("docker-compose.yml") for n in names):
        raise HTTPException(status_code=400, detail="部署包格式异常：缺少 docker-compose.yml")
    if image_reader is None:
        raise HTTPException(status_code=400, detail="部署包格式异常：缺少 mismiss-docker.tar.gz")
    try:
        with tarfile.open(fileobj=image_reader, mode="r:gz") as itf:
            if "manifest.json" not in itf.getnames():
                raise ValueError("缺少 manifest.json")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="部署包内镜像不是标准 docker save 格式（可能由旧版打包脚本生成），请用最新 docker-release 脚本重新打包",
        )


def _backup_deploy(current_version: str) -> None:
    """备份当前部署文件到 .mismiss-backup（供在线回滚）。"""
    if _BACKUP_DIR.exists():
        shutil.rmtree(_BACKUP_DIR)
    _BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    for item in ["docker-compose.yml", "nginx.conf", "config.yml.dist", "deploy.sh", "mismiss-docker.tar.gz"]:
        src = _DEPLOY_DIR / item
        if src.exists():
            shutil.copy2(src, _BACKUP_DIR / item)
    _save_update_state({"backup_dir": str(_BACKUP_DIR), "backup_version": current_version})


def _restore_deploy() -> None:
    """从 .mismiss-backup 恢复部署文件。"""
    if not _BACKUP_DIR.exists():
        raise HTTPException(status_code=400, detail="没有可用的备份，无法回滚")
    for item in ["docker-compose.yml", "nginx.conf", "config.yml.dist", "deploy.sh", "mismiss-docker.tar.gz"]:
        src = _BACKUP_DIR / item
        if src.exists():
            shutil.copy2(src, _DEPLOY_DIR / item)


def _spawn_recreate() -> None:
    """派发一次性容器在宿主守护进程上执行 compose 重建。

    不能在应用容器内直接跑 compose —— 重建会销毁本容器、中断命令；
    通过 ``docker run`` 创建的一次性容器由宿主守护进程独立运行，不受重建影响，
    容器内只负责等待 compose 完成（重建后页面短暂断开属正常现象）。
    """
    home = _deploy_home()
    # 清理上一次遗留的一次性容器（若存在）
    subprocess.run(
        ["docker", "rm", "-f", "mismiss-online-update"],
        capture_output=True, timeout=30,
    )
    cmd = [
        "docker", "run", "--name", "mismiss-online-update",
        "-v", "/var/run/docker.sock:/var/run/docker.sock",
        "-v", f"{home}:/app/deploy",
        "mismiss:latest", "bash", "-c",
        "sleep 3; cd /app/deploy && docker compose --env-file /app/deploy/.env "
        "-f /app/deploy/docker-compose.yml up -d --force-recreate",
    ]
    try:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"启动重建任务失败: {e}")


def _docker_apply(cfg: dict, target_version: str, assets: list[dict]) -> StatusResponse:
    """Docker 在线更新：下载部署包 → 校验 → 备份 → 解压 → 导入镜像 → 后台重建。"""
    asset_url, asset_name = _docker_select_asset(assets, target_version)

    # 下载部署包到宿主部署目录的临时子目录
    if _UPDATE_TMP_DIR.exists():
        shutil.rmtree(_UPDATE_TMP_DIR)
    pkg_path = _UPDATE_TMP_DIR / asset_name
    _download_asset(asset_url, pkg_path, cfg)

    # 校验格式（含内层镜像归档检查，避免 load 时才报 unrecognized image format）
    _verify_docker_package(pkg_path)

    # 备份当前部署包（供在线回滚）
    _backup_deploy(_CURRENT_VERSION)

    # 解压到宿主部署目录（剥离顶层目录；config.yml 用户配置与 .env 不被覆盖）
    try:
        _extract_archive(pkg_path, _DEPLOY_DIR, skip={"config.yml", ".env"})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"部署包解压失败: {e}")

    # 导入新镜像（标准 docker save 格式，任意版本 docker load 可读）
    image_tar = _DEPLOY_DIR / "mismiss-docker.tar.gz"
    if not image_tar.exists():
        raise HTTPException(status_code=400, detail="部署包内缺少 mismiss-docker.tar.gz")
    _run(["docker", "load", "-i", str(image_tar)], timeout=600)

    # 后台重建容器
    _spawn_recreate()

    return StatusResponse(
        success=True,
        message=f"已加载 v{target_version} 镜像，容器正在后台重建（约 10~30 秒），页面将短暂断开",
    )


def _docker_rollback() -> StatusResponse:
    """Docker 在线回滚：恢复备份的部署包 → 重新导入镜像 → 后台重建。"""
    _restore_deploy()
    image_tar = _DEPLOY_DIR / "mismiss-docker.tar.gz"
    _run(["docker", "load", "-i", str(image_tar)], timeout=600)
    _spawn_recreate()
    _save_update_state({})
    return StatusResponse(success=True, message="已恢复上一版本镜像，容器正在后台重建（约 10~30 秒）")


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
        "is_docker": _IS_DOCKER,
        "docker_ready": _docker_ready(),
    }


@router.get("/check")
async def update_check():
    """检测最新版本。"""
    cfg = _update_config()
    releases = _github_request(f"/repos/{cfg['repo']}/releases?per_page=100")
    if not releases:
        return {"latest": None, "up_to_date": True, "releases": []}

    # GitHub Releases 按发布时间倒序，补发的旧版本（如 beta.2 晚于
    # beta.3 发布）会排在最前——按语义版本号重新排序，避免误判
    parsed = [(r, _parse_version(r.get("tag_name", ""))) for r in releases]
    parsed.sort(key=lambda rv: rv[1] or (0, 0, 0, 0, 0, 0), reverse=True)
    sorted_releases = [r for r, _ in parsed]

    latest = sorted_releases[0]
    latest_tag = latest.get("tag_name", "").lstrip("v")
    current_ver = _parse_version(_CURRENT_VERSION)
    latest_ver = parsed[0][1]
    if current_ver is not None and latest_ver is not None:
        # 最新发布版本不高于当前版本 → 无需更新
        up_to_date = latest_ver <= current_ver
    else:
        up_to_date = latest_tag == _CURRENT_VERSION
    return {
        "latest": latest_tag,
        "latest_name": latest.get("name", latest_tag),
        "up_to_date": up_to_date,
        "body": latest.get("body", ""),
        "releases": [
            {
                "tag": r.get("tag_name", "").lstrip("v"),
                "name": r.get("name", ""),
                "published_at": r.get("published_at", ""),
                "body": r.get("body", ""),
                "prerelease": bool(r.get("prerelease", False)),
                "assets": [
                    {"name": a.get("name", ""), "url": a.get("browser_download_url", "")}
                    for a in r.get("assets", [])
                ],
            }
            for r in sorted_releases[:100]
        ],
    }


@router.get("/changelog/{version}")
async def update_changelog(version: str):
    """获取指定版本的更新日志。"""
    cfg = _update_config()
    releases = _github_request(f"/repos/{cfg['repo']}/releases?per_page=100")
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

    Docker 部署：自动选择 Docker 部署包资产（mismiss-<版本>-docker.zip/.tar.gz），
    下载校验后通过 docker.sock 导入镜像并后台重建容器。
    """
    cfg = _update_config()
    target_version = str(body.get("version", "")).strip()
    if not target_version:
        raise HTTPException(status_code=400, detail="必须指定目标版本")

    releases = _github_request(f"/repos/{cfg['repo']}/releases?per_page=100")
    target = None
    for r in releases:
        if r.get("tag_name", "").lstrip("v") == target_version:
            target = r
            break
    if target is None:
        raise HTTPException(status_code=404, detail=f"版本 {target_version} 不存在")

    assets = target.get("assets", [])

    if _IS_DOCKER:
        if not _docker_ready():
            raise HTTPException(status_code=400, detail=_DOCKER_UPDATE_HINT)
        return _docker_apply(cfg, target_version, assets)

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
        # 默认取源码归档（mismiss-<版本>.zip / .tar.gz）。
        # 注意排除 docker 部署包（mismiss-<版本>-docker.zip），那会解压出一堆部署文件
        # 却覆盖不了程序文件。
        preferred = (f"mismiss-{target_version}.zip", f"mismiss-{target_version}.tar.gz")
        for a in assets:
            if a.get("name") in preferred:
                asset_url = a.get("browser_download_url")
                asset_name = a.get("name", "")
                break
        if not asset_url:
            for a in assets:
                name = a.get("name", "")
                if name.endswith((".zip", ".tar.gz")) and "-docker" not in name:
                    asset_url = a.get("browser_download_url")
                    asset_name = name
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

    # 下载更新包并解压覆盖（剥离归档顶层目录；config.yml 用户配置不会被覆盖）
    suffix = ".tar.gz" if asset_name.endswith(".tar.gz") else ".zip"
    tmp_pkg = project_root / "data" / f"update_{target_version}{suffix}"
    try:
        _download_asset(asset_url, tmp_pkg, cfg)
        _extract_archive(tmp_pkg, project_root)
        tmp_pkg.unlink(missing_ok=True)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新包下载/解压失败: {e}")

    return StatusResponse(
        success=True,
        message=f"已更新到 v{target_version}，服务即将重启",
    )


@router.post("/rollback", response_model=StatusResponse)
async def update_rollback(s: MissevanServer = Depends(get_server)):
    """回滚到上一版本。"""
    if _IS_DOCKER:
        if not _docker_ready():
            raise HTTPException(status_code=400, detail=_DOCKER_UPDATE_HINT)
        return _docker_rollback()

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

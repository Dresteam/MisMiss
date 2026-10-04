"""程序更新 API。

以 GitHub Releases 为更新源，支持：
- 版本历史与更新日志查看
- 新版本检测
- 执行更新
- 回滚到上一版本
- 镜像站 / 代理配置
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from core.account import BROADCAST_MAX_LEN, AccountManager, clip_broadcast
from core.config import ServerConfig, write_text_resilient
from core.logging import get_logger
from core.version import CURRENT_VERSION
from api.deps import get_account_manager
from api.schemas import StatusResponse

_log = get_logger("web.api.update")

router = APIRouter()

_GITHUB_REPO = "Dresteam/MisMiss"
_GITHUB_API = "https://api.github.com"
_UPDATE_STATE_FILE = Path("data/update_state.json")

# 用户配置文件 —— 与 api/routes/config.py 的 _CONFIG_PATH 指向同一个文件，
# 提到模块级既便于测试替换，也避免两处各自上溯目录算错
_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent.parent.parent / "config.yml"

# 更新提示消息的默认文案（config.yml 缺省时使用）
_NOTIFY_BEFORE_DEFAULT = "机器人即将更新，稍后自动恢复"
_NOTIFY_AFTER_DEFAULT = "机器人已更新完成，已恢复正常"

# 更新状态文件中记录「重启后补发更新完成提示」的键
_NOTIFY_PENDING_KEY = "notify_pending"

# 更新状态文件中记录「本次更新进度」的键
_APPLY_KEY = "apply"

# 更新进度的状态取值
_APPLY_RUNNING = "running"
_APPLY_DONE = "done"
_APPLY_FAILED = "failed"
# 进程重启后发现的残留 running —— 执行它的进程已经不在了
_APPLY_INTERRUPTED = "interrupted"

# 更新流程的步骤标识（前端按此显示进度文案）
_STEP_LABELS = {
    "prepare": "准备中",
    "download": "下载部署包",
    "verify": "校验部署包",
    "notify": "发送更新提示",
    "backup": "备份当前版本",
    "extract": "解压部署包",
    "load": "导入镜像",
    "recreate": "重建容器",
    "done": "完成",
}

# 是否运行在 Docker 容器内（Docker 会在容器根目录创建 /.dockerenv）
_IS_DOCKER = Path("/.dockerenv").exists()
# docker.sock 是否挂载（在线更新需要）
_DOCKER_SOCKET = Path("/var/run/docker.sock").exists()
# 宿主部署目录（compose 挂载到 /app/deploy）——在线更新在此下载/解压部署包
_DEPLOY_DIR = Path("/app/deploy")
_BACKUP_DIR = _DEPLOY_DIR / ".mismiss-backup"
_UPDATE_TMP_DIR = _DEPLOY_DIR / ".mismiss-update"
# 执行容器重建的一次性容器名（日志见 <部署目录>/logs/update-recreate.log）
_RECREATE_CONTAINER = "mismiss-online-update"

_DOCKER_UPDATE_HINT = (
    "未挂载 docker.sock / 部署目录，在线更新不可用。"
    "请通过部署包手动更新（bash deploy.sh）。"
)

# 版本号统一由 core.version 提供（环境变量 > pyproject.toml > 兜底）
_CURRENT_VERSION = CURRENT_VERSION


# ------------------------------------------------------------------ #
# 配置读取
# ------------------------------------------------------------------ #

def _update_config() -> dict:
    """读取 update 配置（含镜像/代理/更新提示）。"""
    cfg = ServerConfig.load()
    return {
        "repo": cfg.get_str("update.repo", _GITHUB_REPO),
        "mirror": cfg.get_str("update.mirror", ""),
        "proxy": cfg.get_str("update.proxy", ""),
        "notify_enabled": cfg.get_bool("update.notify_enabled", False),
        "notify_before": cfg.get_str("update.notify_before", _NOTIFY_BEFORE_DEFAULT),
        "notify_after": cfg.get_str("update.notify_after", _NOTIFY_AFTER_DEFAULT),
    }


def _save_update_config(
    repo: str,
    mirror: str,
    proxy: str,
    notify_enabled: bool = False,
    notify_before: str = "",
    notify_after: str = "",
) -> None:
    """保存 update 配置到 config.yml（原子写入，避免与其他写入并发时损坏）。

    :raises HTTPException: 读取失败（宁可报错也不能用空字典覆盖写回，
        那会清掉文件里其余所有配置）或写入失败（如 config.yml 只读挂载）
    """
    import yaml
    config_path = _CONFIG_PATH
    data: dict = {}
    if config_path.exists():
        try:
            data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"配置文件读取失败（{config_path}）：{e}"
            )
    data.setdefault("update", {})
    data["update"]["repo"] = repo
    data["update"]["mirror"] = mirror
    data["update"]["proxy"] = proxy
    data["update"]["notify_enabled"] = bool(notify_enabled)
    data["update"]["notify_before"] = notify_before
    data["update"]["notify_after"] = notify_after
    try:
        # sort_keys=False —— 与 /api/config 的写回保持一致，
        # 否则面板每存一次设置就把用户的 config.yml 键序打乱
        write_text_resilient(
            config_path,
            yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        )
    except OSError as e:
        raise HTTPException(
            status_code=500,
            detail=(
                f"配置文件不可写（{config_path}）：{e}。"
                "Docker 部署请确认 docker-compose.yml 中 config.yml 的挂载没有 :ro；"
                "也可以直接在宿主机编辑该文件后重启容器。"
            ),
        )


def _load_update_state() -> dict:
    """加载更新状态（备份信息）。"""
    if _UPDATE_STATE_FILE.exists():
        try:
            return json.loads(_UPDATE_STATE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


# ------------------------------------------------------------------ #
# 更新提示消息
# ------------------------------------------------------------------ #

def _mark_notify_pending(version: str, message: str) -> None:
    """记录「重启后补发更新完成提示」，由下次启动的 lifespan 读取。

    标记先于解压写入 —— 覆盖的文件里不含 ``data/``，所以能存活到重启之后；
    解压失败时由调用方 :func:`_clear_notify_pending` 撤销。
    """
    state = _load_update_state()
    state[_NOTIFY_PENDING_KEY] = {"version": version, "message": message}
    _save_update_state(state)


def _clear_notify_pending() -> None:
    """撤销待发标记（更新失败时调用，避免下次启动误发）。"""
    state = _load_update_state()
    if state.pop(_NOTIFY_PENDING_KEY, None) is not None:
        _save_update_state(state)


async def _notify_livestreams(manager: AccountManager, message: str) -> str:
    """向各直播间发送一条更新提示。

    实际发送走 :meth:`AccountManager.broadcast_to_livestreams`（面板的
    「全局消息」也用同一通道），这里只负责把结果整理成一句摘要。

    :return: 结果摘要，形如 ``成功 2 个 / 跳过 5 个 / 失败 0 个``
    """
    text = clip_broadcast(message)
    if not text:
        return "消息为空，未发送"
    r = await manager.broadcast_to_livestreams(text)
    return f"成功 {r['sent']} 个 / 跳过 {r['skipped']} 个 / 失败 {r['failed']} 个"


async def notify_before_update(manager: AccountManager) -> None:
    """程序更新前：向各直播间发送「即将更新」提示。"""
    cfg = _update_config()
    if not cfg["notify_enabled"]:
        return
    message = cfg["notify_before"]
    if not clip_broadcast(message):
        return
    try:
        await _notify_livestreams(manager, message)
    except Exception as e:
        # 提示失败不应阻断更新
        _log.warning("更新前提示发送失败: {}", e)


async def notify_after_update(manager: AccountManager) -> None:
    """程序更新重启后：补发上一轮更新留下的「更新完成」提示。

    无待发标记时直接返回 —— 普通重启不会触发。标记无论发送成败都会清除，
    避免每次重启重复发送。
    """
    state = _load_update_state()
    pending = state.get(_NOTIFY_PENDING_KEY)
    if not isinstance(pending, dict):
        return
    state.pop(_NOTIFY_PENDING_KEY, None)
    _save_update_state(state)

    version = str(pending.get("version", "?"))
    message = pending.get("message", "")
    if not clip_broadcast(message):
        return
    try:
        summary = await _notify_livestreams(manager, message)
        _log.info("更新完成提示已处理（v{}）: {}", version, summary)
    except Exception as e:
        _log.warning("更新完成提示发送失败: {}", e)


def _save_update_state(state: dict) -> None:
    """整表覆盖写（原子：先写临时文件再 os.replace）。

    ⚠️ 会用传入的字典**整个替换**文件内容，调用方若只想改一个键请用
    :func:`_patch_update_state`，否则会把 ``backup_dir`` / ``notify_pending``
    等别的键一起抹掉。
    """
    _UPDATE_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = _UPDATE_STATE_FILE.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    os.replace(tmp, _UPDATE_STATE_FILE)


def _patch_update_state(**fields) -> dict:
    """读-改-写地合并若干键，其余键原样保留。

    传 ``None`` 表示删除该键。

    :return: 合并后的完整状态字典
    """
    state = _load_update_state()
    for k, v in fields.items():
        if v is None:
            state.pop(k, None)
        else:
            state[k] = v
    _save_update_state(state)
    return state


# ------------------------------------------------------------------ #
# 本次更新的进度（供前端轮询）
# ------------------------------------------------------------------ #

def _read_apply_progress() -> dict:
    """读取当前/最近一次更新的进度；没有记录时返回 ``{"state": "idle"}``。"""
    data = _load_update_state().get(_APPLY_KEY)
    if not isinstance(data, dict):
        return {"state": "idle"}
    # 补上人可读的步骤文案，前端不必自己维护映射
    if data.get("step"):
        data["step_label"] = _STEP_LABELS.get(str(data["step"]), str(data["step"]))
    return data


def _set_apply_progress(
    kind: str,
    state: str,
    step: str,
    message: str = "",
    version: str = "",
) -> None:
    """写入更新进度（读-改-写，不动其它键）。"""
    prev = _load_update_state().get(_APPLY_KEY)
    prev = prev if isinstance(prev, dict) else {}
    # 上一轮也是 running 说明是同一次更新的步骤推进，沿用开始时间；
    # 否则视为新的一轮，重新计时。
    started = prev.get("started_at") if prev.get("state") == _APPLY_RUNNING else None
    record = {
        "kind": kind,
        "state": state,
        "step": step,
        "step_label": _STEP_LABELS.get(step, step),
        "message": message,
        "version": version or prev.get("version", ""),
        "started_at": started or time.time(),
        "finished_at": None if state == _APPLY_RUNNING else time.time(),
    }
    _patch_update_state(**{_APPLY_KEY: record})


def mark_interrupted_if_running() -> None:
    """启动时调用：把残留的 running 判定为 interrupted。

    执行更新的进程已经不在了（Docker 重建换了容器 / 非 Docker 解压覆盖 ``src/``
    触发了 uvicorn reload），所以任何 ``running`` 都必然是中断残留。
    """
    data = _load_update_state().get(_APPLY_KEY)
    if not isinstance(data, dict) or data.get("state") != _APPLY_RUNNING:
        return
    _set_apply_progress(
        kind=str(data.get("kind", "apply")),
        state=_APPLY_INTERRUPTED,
        step="done",
        message="上一次更新未完成即中断（进程已重启）。请查看日志 logs/update-recreate.log 后重试。",
        version=str(data.get("version", "")),
    )
    _log.warning("发现中断的更新任务（step={}），已标记为 interrupted", data.get("step"))


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
            # 分块落盘，不要 resp.read() —— 部署包 200MB+，整个读进内存会把
            # 512MB 上限的容器顶到边缘（应用基线已占 270MB 左右）
            shutil.copyfileobj(resp, f, length=256 * 1024)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新包下载失败: {e}")


def _verify_docker_package(pkg_path: Path) -> None:
    """校验 Docker 部署包：含 docker-compose.yml 与 mismiss-docker.tar.gz，
    且内层镜像归档是标准 docker save 格式（根含 manifest.json）。

    ⚠️ 全程流式读取，**不得**把内层归档整个读进内存。镜像归档 200MB+，
    容器内存上限常见 512MB，读一份再拷一份就会把进程 OOM 掉 ——
    线上就是这么「更新失败」的，而且发生在备份之前，现场毫无痕迹。
    """
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
                # ⚠️ 必须用 zf.open（流）而不是 io.BytesIO(zf.read(n))。
                # 后者会把 200MB+ 的镜像归档整个读进内存，再被 BytesIO 拷一份，
                # 峰值 400MB+ —— 容器内存上限 512MB 时直接把进程 OOM 掉，
                # 表现为「包下载完了但更新失败」，且因为发生在备份之前，
                # 连备份目录都不会更新，现场没有任何痕迹。
                image_reader = zf.open(n)
                break

    if not any(n.endswith("docker-compose.yml") for n in names):
        raise HTTPException(status_code=400, detail="部署包格式异常：缺少 docker-compose.yml")
    if image_reader is None:
        raise HTTPException(status_code=400, detail="部署包格式异常：缺少 mismiss-docker.tar.gz")
    try:
        # 同样用流式模式（r|gz）逐成员读，找到 manifest.json 即停。
        # getnames() 会先把整个 tar 扫一遍建索引，在流上没必要。
        found = False
        with tarfile.open(fileobj=image_reader, mode="r|gz") as itf:
            for member in itf:
                if member.name == "manifest.json":
                    found = True
                    break
        if not found:
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
    # 只并这两个键 —— 整表覆盖会抹掉同一文件里的 apply 进度与 notify_pending
    _patch_update_state(backup_dir=str(_BACKUP_DIR), backup_version=current_version)


def _restore_deploy() -> None:
    """从 .mismiss-backup 恢复部署文件。"""
    if not _BACKUP_DIR.exists():
        raise HTTPException(status_code=400, detail="没有可用的备份，无法回滚")
    for item in ["docker-compose.yml", "nginx.conf", "config.yml.dist", "deploy.sh", "mismiss-docker.tar.gz"]:
        src = _BACKUP_DIR / item
        if src.exists():
            shutil.copy2(src, _DEPLOY_DIR / item)


def _recreate_container_running() -> bool:
    """上一次派发的一次性重建容器是否仍在运行。"""
    try:
        proc = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", _RECREATE_CONTAINER],
            capture_output=True, text=True, timeout=30,
        )
    except Exception:
        return False
    return proc.returncode == 0 and proc.stdout.strip() == "true"


def _spawn_recreate() -> None:
    """派发一次性容器在宿主守护进程上执行 compose 重建。

    不能在应用容器内直接跑 compose —— 重建会销毁本容器、中断命令；
    通过 ``docker run`` 创建的一次性容器由宿主守护进程独立运行，不受重建影响，
    容器内只负责等待 compose 完成（重建后页面短暂断开属正常现象）。

    输出**追加写** ``<部署目录>/logs/update-recreate.log``，不再丢弃 ——
    重建是整条链路最容易静默失败的一步，日志是唯一的证据。
    """
    home = _deploy_home()

    # 仍在运行的容器**不能杀**：它可能正在 compose 重建，半路杀掉会把栈留在
    # 半重建状态（旧容器已停、新容器没起）。只有已退出/不存在时才清理。
    if _recreate_container_running():
        raise HTTPException(
            status_code=409,
            detail="上一次的容器重建仍在进行中，请等它结束后再试（约 10~30 秒）",
        )
    subprocess.run(
        ["docker", "rm", "-f", _RECREATE_CONTAINER],
        capture_output=True, timeout=30,
    )

    cmd = [
        "docker", "run", "--name", _RECREATE_CONTAINER,
        "-v", "/var/run/docker.sock:/var/run/docker.sock",
        "-v", f"{home}:/app/deploy",
        "mismiss:latest", "bash", "-c",
        "sleep 3; cd /app/deploy && docker compose --env-file /app/deploy/.env "
        "-f /app/deploy/docker-compose.yml up -d --force-recreate",
    ]
    # ⚠️ 日志路径必须用**容器内**的挂载点（_DEPLOY_DIR），不能拼 .env 里的宿主路径。
    # _deploy_home() 返回的是宿主绝对路径（如 /www/wwwroot/MisMiss），那是给下面
    # `docker run -v` 挂载用的；它在本容器内**并不存在**，拿它写文件会让
    # mkdir(parents=True) 试图从根开始创建 /www/... 整条链 —— 应用以 mismiss
    # （非 root）运行，创建 /www 直接 EACCES，报「Permission denied: '/www'」，
    # 更新就卡在最后一步派发重建上。
    # _DEPLOY_DIR 本身就是宿主部署目录的挂载点，写它等于写宿主的 logs/。
    log_path = _DEPLOY_DIR / "logs" / "update-recreate.log"
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "ab") as log:
            log.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} 重建开始 =====\n".encode())
            log.flush()
            # Popen 会为子进程复制一份 fd，父进程这边 with 退出即可
            subprocess.Popen(
                cmd, stdout=log, stderr=subprocess.STDOUT, start_new_session=True
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"启动重建任务失败: {e}")


async def _docker_apply(
    manager: AccountManager,
    cfg: dict,
    target_version: str,
    assets: list[dict],
) -> None:
    """Docker 在线更新：下载部署包 → 校验 → 备份 → 解压 → 导入镜像 → 后台重建。

    在后台任务里跑（见 :func:`_run_update_task`），不持有任何 HTTP 请求。
    所有阻塞调用一律经 ``asyncio.to_thread`` 移出事件循环 —— ``docker load``
    动辄几十秒到几分钟，直接跑在循环上会让整个面板与健康检查一起停摆
    （``docs/TASKS.md`` 的 P2）。
    """
    asset_url, asset_name = _docker_select_asset(assets, target_version)

    # 下载部署包到宿主部署目录的临时子目录
    _set_apply_progress("apply", _APPLY_RUNNING, "download",
                        f"正在下载 {asset_name}（较大，请耐心等待）", target_version)
    if await asyncio.to_thread(_UPDATE_TMP_DIR.exists):
        await asyncio.to_thread(shutil.rmtree, _UPDATE_TMP_DIR)
    pkg_path = _UPDATE_TMP_DIR / asset_name
    await asyncio.to_thread(_download_asset, asset_url, pkg_path, cfg)

    # 校验格式（含内层镜像归档检查，避免 load 时才报 unrecognized image format）
    _set_apply_progress("apply", _APPLY_RUNNING, "verify", "正在校验部署包", target_version)
    await asyncio.to_thread(_verify_docker_package, pkg_path)

    # 容器重建前先把「即将更新」提示发出去（此后镜像导入耗时较长，队列有充足时间排空）
    notify_after = cfg["notify_after"]
    if cfg["notify_enabled"] and clip_broadcast(cfg["notify_before"]):
        _set_apply_progress("apply", _APPLY_RUNNING, "notify", "正在发送更新提示", target_version)
        await _notify_livestreams(manager, cfg["notify_before"])

    # 备份当前部署包（供在线回滚）
    _set_apply_progress("apply", _APPLY_RUNNING, "backup", "正在备份当前版本", target_version)
    await asyncio.to_thread(_backup_deploy, _CURRENT_VERSION)
    # 记录待发提示：容器重建后由新进程 lifespan 补发（data/ 是挂载卷，能存活到重启后）
    if cfg["notify_enabled"] and clip_broadcast(notify_after):
        _mark_notify_pending(target_version, notify_after)

    # 解压到宿主部署目录（剥离顶层目录；config.yml 用户配置与 .env 不被覆盖）
    _set_apply_progress("apply", _APPLY_RUNNING, "extract", "正在解压部署包", target_version)
    try:
        await asyncio.to_thread(
            _extract_archive, pkg_path, _DEPLOY_DIR, {"config.yml", ".env"}
        )
    except HTTPException:
        _clear_notify_pending()
        raise
    except Exception as e:
        _clear_notify_pending()
        raise HTTPException(status_code=500, detail=f"部署包解压失败: {e}")

    # 导入新镜像（标准 docker save 格式，任意版本 docker load 可读）
    image_tar = _DEPLOY_DIR / "mismiss-docker.tar.gz"
    if not await asyncio.to_thread(image_tar.exists):
        raise HTTPException(status_code=400, detail="部署包内缺少 mismiss-docker.tar.gz")
    _set_apply_progress("apply", _APPLY_RUNNING, "load",
                        "正在导入镜像（视机器性能约 1~3 分钟，请勿关闭页面）", target_version)
    await asyncio.to_thread(_run, ["docker", "load", "-i", str(image_tar)], 600)

    # 派发容器重建：此后本进程随时可能被替换
    _set_apply_progress("apply", _APPLY_RUNNING, "recreate",
                        "正在重建容器，页面将短暂断开", target_version)
    await asyncio.to_thread(_spawn_recreate)


async def _docker_rollback() -> None:
    """Docker 在线回滚：恢复备份的部署包 → 重新导入镜像 → 后台重建。"""
    _set_apply_progress("rollback", _APPLY_RUNNING, "backup", "正在恢复备份的部署文件")
    await asyncio.to_thread(_restore_deploy)
    image_tar = _DEPLOY_DIR / "mismiss-docker.tar.gz"
    _set_apply_progress("rollback", _APPLY_RUNNING, "load", "正在导入上一版镜像")
    await asyncio.to_thread(_run, ["docker", "load", "-i", str(image_tar)], 600)
    _set_apply_progress("rollback", _APPLY_RUNNING, "recreate", "正在重建容器，页面将短暂断开")
    await asyncio.to_thread(_spawn_recreate)
    # 只清备份键，别整表覆盖 —— 同文件里还可能有 notify_pending
    _patch_update_state(backup_dir=None, backup_version=None)


# ================================================================== #
# 后台任务调度
# ================================================================== #

# 当前正在跑的更新/回滚任务。持引用既用于「是否忙」的快失败探测，
# 也避免 create_task 的返回值被 GC 掉导致任务中途消失。
_update_task: asyncio.Task | None = None


def update_busy() -> bool:
    """是否有更新/回滚正在执行。"""
    return _update_task is not None and not _update_task.done()


async def _run_update_task(kind: str, target_version: str, job) -> None:
    """后台执行一次更新/回滚（``job`` 是无参协程），终态写进 ``update_state.json``。

    成功时写 ``done`` —— 注意此时容器重建只是**已派发**，是否真的起来要看
    重启后的进程，所以文案里带上日志路径，别把话说满。
    """
    try:
        await job()
    except HTTPException as e:
        detail = str(e.detail)
        _set_apply_progress(kind, _APPLY_FAILED, "done", detail, target_version)
        _log.error("更新失败（{}）: {}", kind, detail)
    except Exception as e:
        _set_apply_progress(
            kind, _APPLY_FAILED, "done",
            f"未预期的错误: {e}。详见 logs/bot_*.log", target_version,
        )
        _log.exception("更新失败（{}）", kind)
    else:
        _set_apply_progress(
            kind, _APPLY_DONE, "done",
            f"已派发容器重建（v{target_version}）。若约 1 分钟后版本仍未变化，"
            f"请查看 logs/update-recreate.log",
            target_version,
        )
        _log.info("更新流程已完成并派发重建（v{}）", target_version)
    finally:
        # 非 Docker 路径会解压覆盖 src/ 触发 reload，正常情况走不到这里
        global _update_task
        _update_task = None


def _start_update_task(kind: str, target_version: str, job) -> None:
    """占用更新通道并起后台任务；已在执行时抛 409。

    检查与赋值之间**没有 await**，单线程事件循环下不会被插队。
    """
    global _update_task
    if update_busy():
        raise HTTPException(
            status_code=409,
            detail="已有更新正在进行中，请等它结束（可在本页查看进度）",
        )
    _set_apply_progress(kind, _APPLY_RUNNING, "prepare", "正在准备更新", target_version)
    _update_task = asyncio.create_task(
        _run_update_task(kind, target_version, job)
    )


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
        "notify_enabled": cfg["notify_enabled"],
        "notify_before": cfg["notify_before"],
        "notify_after": cfg["notify_after"],
        "notify_max_len": BROADCAST_MAX_LEN,
        "has_backup": bool(state.get("backup_dir")),
        "backup_version": state.get("backup_version", ""),
        "is_docker": _IS_DOCKER,
        "docker_ready": _docker_ready(),
    }


@router.get("/check")
async def update_check():
    """检测最新版本。"""
    cfg = _update_config()
    releases = await asyncio.to_thread(
        _github_request, f"/repos/{cfg['repo']}/releases?per_page=100"
    )
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
    releases = await asyncio.to_thread(
        _github_request, f"/repos/{cfg['repo']}/releases?per_page=100"
    )
    for r in releases:
        tag = r.get("tag_name", "").lstrip("v")
        if tag == version:
            return {"version": tag, "name": r.get("name", ""), "body": r.get("body", "")}
    raise HTTPException(status_code=404, detail=f"版本 {version} 不存在")


@router.post("/settings", response_model=StatusResponse)
async def update_settings(body: dict, manager: AccountManager = Depends(get_account_manager)):
    """保存更新配置（镜像站 / 代理 / 更新提示消息）。

    只更新请求体里**出现过的**键，未出现的保持原值 —— 面板的「启用更新提示」
    开关是点一下即时落盘的，不能顺带把用户还没点保存的其它输入一起写进去。
    """
    cur = _update_config()

    repo = str(body["repo"]).strip() or _GITHUB_REPO if "repo" in body else cur["repo"]
    mirror = str(body["mirror"]).strip() if "mirror" in body else cur["mirror"]
    proxy = str(body["proxy"]).strip() if "proxy" in body else cur["proxy"]
    notify_enabled = (
        bool(body["notify_enabled"]) if "notify_enabled" in body
        else cur["notify_enabled"]
    )
    notify_before = (
        clip_broadcast(body["notify_before"]) if "notify_before" in body
        else cur["notify_before"]
    )
    notify_after = (
        clip_broadcast(body["notify_after"]) if "notify_after" in body
        else cur["notify_after"]
    )

    _save_update_config(
        repo, mirror, proxy, notify_enabled, notify_before, notify_after
    )
    return StatusResponse(success=True, message="更新配置已保存")


@router.get("/status")
async def update_status():
    """本次（或最近一次）更新的进度，供前端轮询。"""
    return {"busy": update_busy(), **_read_apply_progress()}


@router.post("/apply", response_model=StatusResponse, status_code=202)
async def update_apply(body: dict, manager: AccountManager = Depends(get_account_manager)):
    """执行更新到指定版本。

    请求体：``{"version": "1.0.0-beta.4", "asset_name": "mismiss.zip"}``

    Docker 部署：自动选择 Docker 部署包资产（mismiss-<版本>-docker.zip/.tar.gz），
    下载校验后通过 docker.sock 导入镜像并后台重建容器。
    """
    cfg = _update_config()
    target_version = str(body.get("version", "")).strip()
    if not target_version:
        raise HTTPException(status_code=400, detail="必须指定目标版本")

    releases = await asyncio.to_thread(
        _github_request, f"/repos/{cfg['repo']}/releases?per_page=100"
    )
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
        _start_update_task(
            "apply", target_version,
            lambda: _docker_apply(manager, cfg, target_version, assets),
        )
        return StatusResponse(
            success=True,
            message=f"已开始更新到 v{target_version}，可在本页查看进度",
        )

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

    _start_update_task(
        "apply", target_version,
        lambda: _apply_source(manager, cfg, target_version, asset_url, asset_name),
    )
    return StatusResponse(
        success=True,
        message=f"已开始更新到 v{target_version}，可在本页查看进度",
    )


async def _apply_source(
    manager: AccountManager,
    cfg: dict,
    target_version: str,
    asset_url: str,
    asset_name: str,
) -> None:
    """非 Docker 在线更新：下载源码归档 → 备份 → 解压覆盖程序目录。

    ⚠️ 解压覆盖 ``src/`` 会触发 uvicorn 的 reload 监视器重启进程，
    **执行本函数的后台任务会随之被杀**。所以「成功」必须在解压完成后立刻落盘，
    且启动时要能把残留的 ``running`` 识别成中断（见
    :func:`mark_interrupted_if_running`）。
    """
    project_root = Path(__file__).resolve().parent.parent.parent.parent.parent
    suffix = ".tar.gz" if asset_name.endswith(".tar.gz") else ".zip"
    tmp_pkg = project_root / "data" / f"update_{target_version}{suffix}"

    # 先只下载到 data/ 下的临时文件（不动程序文件），
    # 下载这一步是整条链路最可能失败的地方
    _set_apply_progress("apply", _APPLY_RUNNING, "download",
                        f"正在下载 {asset_name}", target_version)
    try:
        await asyncio.to_thread(_download_asset, asset_url, tmp_pkg, cfg)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新包下载失败: {e}")

    # 走到这里更新已无退路：解压覆盖 src/ 会触发 uvicorn 的 reload 监视器重启进程，
    # 故必须在写文件之前把「即将更新」提示真正发出去（内部会等队列排空）
    if cfg["notify_enabled"] and clip_broadcast(cfg["notify_before"]):
        _set_apply_progress("apply", _APPLY_RUNNING, "notify", "正在发送更新提示", target_version)
        await _notify_livestreams(manager, cfg["notify_before"])

    # 备份当前版本
    _set_apply_progress("apply", _APPLY_RUNNING, "backup", "正在备份当前版本", target_version)
    backup_dir = project_root / "data" / "backup" / f"v{_CURRENT_VERSION}"
    try:
        if await asyncio.to_thread(backup_dir.exists):
            await asyncio.to_thread(shutil.rmtree, backup_dir)
        await asyncio.to_thread(backup_dir.parent.mkdir, parents=True, exist_ok=True)

        def _copy_tree() -> None:
            for item in ["src", "web", "plugins", "scripts", "config.yml"]:
                src = project_root / item
                if not src.exists():
                    continue
                dst = backup_dir / item
                if src.is_dir():
                    shutil.copytree(src, dst)
                else:
                    shutil.copy2(src, dst)

        await asyncio.to_thread(_copy_tree)
        # 只并这两个键，别整表覆盖（同文件里还有 notify_pending）
        _patch_update_state(backup_dir=str(backup_dir), backup_version=_CURRENT_VERSION)
    except Exception as e:
        tmp_pkg.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"备份失败: {e}")

    # 记录待发提示：进程重启后由新进程 lifespan 补发（data/ 不在覆盖范围内，能存活）
    if cfg["notify_enabled"] and clip_broadcast(cfg["notify_after"]):
        _mark_notify_pending(target_version, cfg["notify_after"])

    # 解压覆盖（剥离归档顶层目录；config.yml 用户配置不会被覆盖）
    _set_apply_progress("apply", _APPLY_RUNNING, "extract", "正在解压并覆盖程序文件", target_version)
    try:
        await asyncio.to_thread(_extract_archive, tmp_pkg, project_root)
        await asyncio.to_thread(tmp_pkg.unlink, True)
    except HTTPException:
        _clear_notify_pending()
        raise
    except Exception as e:
        _clear_notify_pending()
        raise HTTPException(status_code=500, detail=f"更新包解压失败: {e}")


@router.post("/rollback", response_model=StatusResponse, status_code=202)
async def update_rollback(manager: AccountManager = Depends(get_account_manager)):
    """回滚到上一版本。"""
    if _IS_DOCKER:
        if not _docker_ready():
            raise HTTPException(status_code=400, detail=_DOCKER_UPDATE_HINT)
        _start_update_task("rollback", _CURRENT_VERSION, _docker_rollback)
        return StatusResponse(success=True, message="已开始回滚，可在本页查看进度")

    state = _load_update_state()
    backup_dir = state.get("backup_dir", "")
    if not backup_dir or not await asyncio.to_thread(Path(backup_dir).exists):
        raise HTTPException(status_code=400, detail="没有可用的备份，无法回滚")

    prev_version = str(state.get("backup_version", "?"))
    _start_update_task(
        "rollback", prev_version,
        lambda: _rollback_source(backup_dir, prev_version),
    )
    return StatusResponse(success=True, message="已开始回滚，可在本页查看进度")


async def _rollback_source(backup_dir: str, prev_version: str) -> None:
    """非 Docker 回滚：用备份目录覆盖程序文件。

    与 :func:`_apply_source` 一样，覆盖会触发 reload 重启进程。
    """
    project_root = Path(__file__).resolve().parent.parent.parent.parent.parent
    _set_apply_progress("rollback", _APPLY_RUNNING, "extract",
                        f"正在恢复 v{prev_version} 的文件", prev_version)

    def _restore() -> None:
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

    try:
        await asyncio.to_thread(_restore)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"回滚失败: {e}")

    # 只清备份键，别整表覆盖 —— 同文件里还可能有 notify_pending
    _patch_update_state(backup_dir=None, backup_version=None)

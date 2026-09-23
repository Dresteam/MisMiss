"""服务器配置 & 日志等级 API。"""

from __future__ import annotations

import os
import sys
import json
import logging
import asyncio
from pathlib import Path

import yaml
from fastapi import APIRouter, Depends, HTTPException

from core.account import AccountManager
from core.config import ServerConfig, write_text_resilient
from api.deps import get_account_manager

router = APIRouter()

# 持久化路径：PyInstaller 模式下使用 exe 所在目录
if getattr(sys, "frozen", False):
    _HOME = Path(os.environ.get("MISMISS_HOME", Path(sys.executable).parent))
else:
    _HOME = Path(__file__).resolve().parent.parent.parent.parent.parent

_CONFIG_PATH = str(_HOME / "config.yml")
_PROJECT_ROOT = _HOME


def _read_config_file() -> dict:
    """读取 config.yml，读不出来时给出可读报错。

    宁可报错也不返回空字典 —— 调用方拿到空字典再写回，会把其余配置全部抹掉。
    """
    if not os.path.exists(_CONFIG_PATH):
        return {}
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError) as e:
        raise HTTPException(
            status_code=500, detail=f"配置文件读取失败（{_CONFIG_PATH}）：{e}"
        )


def _write_config_file(data: dict) -> None:
    """写回 config.yml，失败时给出可操作的提示而不是裸 500。"""
    try:
        write_text_resilient(
            _CONFIG_PATH,
            yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False),
        )
    except OSError as e:
        raise HTTPException(
            status_code=500,
            detail=(
                f"配置文件不可写（{_CONFIG_PATH}）：{e}。"
                "Docker 部署请确认 docker-compose.yml 中 config.yml 的挂载没有 :ro；"
                "也可以直接在宿主机编辑该文件后重启容器。"
            ),
        )


# ================================================================== #
# GET  /api/config —— 读取完整配置
# ================================================================== #

@router.get("/config")
async def get_config():
    """返回当前生效的配置（合并默认值后的结果）。"""
    cfg = ServerConfig.load(_CONFIG_PATH)
    return {
        "config": cfg._data,
        "path": _CONFIG_PATH,
    }


# ================================================================== #
# PUT  /api/config —— 部分更新配置
# ================================================================== #

@router.put("/config")
async def update_config(body: dict):
    """合并写入配置——仅更新传入的键，其他保持不变。"""
    try:
        current = _read_config_file()
        # 深度合并
        _deep_merge(current, body.get("config", {}))
        _write_config_file(current)
        return {"success": True, "message": "配置已保存"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ================================================================== #
# GET  /api/config/log-level —— 查看当前日志等级
# ================================================================== #

@router.get("/config/log-level")
async def get_log_level():
    """获取当前 loguru 和 stdlib 的日志等级。"""
    levels = {}

    # loguru
    try:
        from loguru import logger as _loguru_logger
        # loguru 没有直接获取全局 level 的方法，返回每个 handler 的信息
        levels["loguru"] = "active"
    except ImportError:
        levels["loguru"] = "not installed"

    # stdlib root logger
    root = logging.getLogger()
    levels["stdlib_root"] = logging.getLevelName(root.level)

    return levels


# ================================================================== #
# PUT  /api/config/log-level —— 更改日志输出等级
# ================================================================== #

@router.put("/config/log-level")
async def set_log_level(body: dict):
    """动态修改日志输出等级。

    body: {"level": "DEBUG" | "INFO" | "WARNING" | "ERROR" | "CRITICAL"}
    """
    level_name = body.get("level", "INFO").upper()
    valid = {"DEBUG": 10, "INFO": 20, "SUCCESS": 25, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}

    if level_name not in valid:
        raise HTTPException(status_code=400, detail=f"无效的日志等级: {level_name}")

    # 先落盘再改内存 —— 写不进去就直接报错，避免出现「返回 500 但级别其实已经变了」
    current = _read_config_file()
    current.setdefault("logging", {})["level"] = level_name
    _write_config_file(current)

    # stdlib
    logging.getLogger().setLevel(valid[level_name])

    # loguru — update level on existing handlers
    try:
        from loguru import logger as _loguru_logger
        for handler_id, handler_config in list(_loguru_logger._core.handlers.items()):
            _loguru_logger._core.handlers[handler_id]._levelno = valid[level_name]
    except Exception:
        pass

    # 同步更新 WebSocket sink 的日志等级
    try:
        from api.routes.ws import set_ws_log_level
        set_ws_log_level(level_name)
    except Exception:
        pass

    return {"success": True, "message": f"日志等级已设为 {level_name}，已持久化到 config.yml"}


# ================================================================== #
# 端口修改 + 重启
# ================================================================== #

@router.put("/config/ports")
async def update_ports(
    body: dict, manager: AccountManager = Depends(get_account_manager)
):
    """修改 API 端口，保存配置后立即重启后端。Web 端口只能通过启动脚本修改。"""
    api_port = body.get("api_port", 8080)

    # 只保存 api_port，web_port 保持不变
    # 先落盘再停机 —— 写不进去就别把账户全关掉
    current = _read_config_file()
    current.setdefault("server", {})["api_port"] = api_port
    _write_config_file(current)

    # 关闭全部账户运行时
    await manager.shutdown_all()

    # 0.5s 后重启后端
    def _restart():
        os.execv(sys.executable, [
            sys.executable, "-m", "web.backend.main", "--port", str(api_port)
        ])

    loop = asyncio.get_running_loop()
    loop.call_later(0.5, _restart)

    return {"success": True, "message": f"API 端口已改为 {api_port}，后端即将重启"}


# ================================================================== #
# pip 安装
# ================================================================== #

@router.post("/config/pip-install")
async def pip_install(body: dict):
    """安装 pip 包（管理员）。"""
    pkg = body.get("package", "").strip()
    if not pkg:
        raise HTTPException(status_code=400, detail="请输入包名")
    # 包名以 "-" 开头会被 pip 当作命令行选项（--target / -r / --index-url 等），
    # 等于把参数注入交给调用方；此处直接拒绝。
    if pkg.startswith("-"):
        raise HTTPException(status_code=400, detail="包名不能以 '-' 开头")
    if len(pkg) > 200:
        raise HTTPException(status_code=400, detail="包名过长")

    try:
        from pip._internal.cli.main import main as pip_main
        exit_code = pip_main(["install", "--quiet", "--no-input", pkg])
        if exit_code != 0:
            raise HTTPException(status_code=500, detail=f"pip install 失败 (exit {exit_code})")
        return {"success": True, "message": f"{pkg} 已安装"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ================================================================== #
# 工具
# ================================================================== #

def _deep_merge(base: dict, override: dict) -> None:
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value

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

from core import MissevanServer
from core.config import ServerConfig
from api.deps import get_server
from api.schemas import BotCookieResponse

router = APIRouter()

# 持久化路径：PyInstaller 模式下使用 exe 所在目录
if getattr(sys, "frozen", False):
    _HOME = Path(os.environ.get("MISMISS_HOME", Path(sys.executable).parent))
else:
    _HOME = Path(__file__).resolve().parent.parent.parent.parent.parent

_CONFIG_PATH = str(_HOME / "config.yml")
_PROJECT_ROOT = _HOME


# ================================================================== #
# GET  /api/config —— 读取完整配置
# ================================================================== #

@router.get("/config")
async def get_config(s: MissevanServer = Depends(get_server)):
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
async def update_config(body: dict, s: MissevanServer = Depends(get_server)):
    """合并写入配置——仅更新传入的键，其他保持不变。"""
    try:
        # 读取当前文件内容
        current: dict = {}
        if os.path.exists(_CONFIG_PATH):
            with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
                current = yaml.safe_load(f) or {}

        # 深度合并
        _deep_merge(current, body.get("config", {}))

        # 写回
        with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
            yaml.dump(current, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

        return {"success": True, "message": "配置已保存"}
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

    # 持久化到 config.yml
    current = {}
    if os.path.exists(_CONFIG_PATH):
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            current = yaml.safe_load(f) or {}
    current.setdefault("logging", {})["level"] = level_name
    with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(current, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    return {"success": True, "message": f"日志等级已设为 {level_name}，已持久化到 config.yml"}


# ================================================================== #
# 端口修改 + 重启
# ================================================================== #

@router.put("/config/ports")
async def update_ports(body: dict, s: MissevanServer = Depends(get_server)):
    """修改 API 端口，保存配置后立即重启后端。Web 端口只能通过启动脚本修改。"""
    api_port = body.get("api_port", 8080)

    # 只保存 api_port，web_port 保持不变
    current: dict = {}
    if os.path.exists(_CONFIG_PATH):
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            current = yaml.safe_load(f) or {}
    current.setdefault("server", {})["api_port"] = api_port
    with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(current, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    # 关闭当前服务器
    await s.shutdown()

    # 0.5s 后重启后端
    def _restart():
        os.execv(sys.executable, [
            sys.executable, "-m", "web.backend.main", "--port", str(api_port)
        ])

    loop = asyncio.get_running_loop()
    loop.call_later(0.5, _restart)

    return {"success": True, "message": f"API 端口已改为 {api_port}，后端即将重启"}


# ================================================================== #
# Cookie 直读（无需权限，仅供管理面板使用）
# ================================================================== #

@router.get("/config/cookie", response_model=BotCookieResponse)
async def read_cookie(s: MissevanServer = Depends(get_server)):
    """从持久化文件直接读取 Cookie，无需 EXPOSE_COOKIE 权限。"""
    state_path = os.path.join(s._data_dir, s._state_file)
    if not os.path.exists(state_path):
        raise HTTPException(status_code=404, detail="未找到持久化数据文件")
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            state = json.load(f)
        cookie = state.get("bot", {}).get("cookie", "")
        return BotCookieResponse(cookie=cookie, length=len(cookie))
    except (json.JSONDecodeError, OSError) as e:
        raise HTTPException(status_code=500, detail=f"读取失败: {e}")


# ================================================================== #
# pip 安装
# ================================================================== #

@router.post("/config/pip-install")
async def pip_install(body: dict):
    """安装 pip 包。"""
    pkg = body.get("package", "").strip()
    if not pkg:
        raise HTTPException(status_code=400, detail="请输入包名")

    try:
        from pip._internal.cli.main import main as pip_main
        exit_code = pip_main(["install", "--quiet", pkg])
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

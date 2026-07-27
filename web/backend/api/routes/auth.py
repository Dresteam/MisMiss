"""
Simple authentication — username/password stored in data/auth.json.
Password hashed with SHA-256, token-based session in memory.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import sys
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, Header, Request
from fastapi.responses import JSONResponse

router = APIRouter()

# 持久化路径：PyInstaller 模式下使用 exe 所在目录，而非临时解压目录
if getattr(sys, "frozen", False):
    _HOME = Path(os.environ.get("MISMISS_HOME", Path(sys.executable).parent))
else:
    _HOME = Path(__file__).resolve().parent.parent.parent.parent.parent

AUTH_FILE = _HOME / "data" / "auth.json"
TOKEN_DIR = _HOME / "data" / "tokens"
TOKEN_TTL = 30 * 24 * 3600  # 30 days


def _hash(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


# ------------------------------------------------------------------ #
# 文件级 token 存储（多 worker 共享）
# ------------------------------------------------------------------ #
# Gunicorn 多 worker 模式下每个 worker 有独立内存，必须落盘才能在
# worker 间共享 session。每个 token 存为一个文件，文件名 = token，
# 内容 = JSON {username, expires}。
# ------------------------------------------------------------------ #
TOKEN_DIR.mkdir(parents=True, exist_ok=True)


def _save_token(token: str, username: str, expires: float) -> None:
    """持久化 token 到文件。"""
    path = TOKEN_DIR / token
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"username": username, "expires": expires}, f)


def _load_token(token: str) -> dict | None:
    """从文件加载 token 数据，过期自动删除。"""
    path = TOKEN_DIR / token
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    if time.time() > data.get("expires", 0):
        try:
            os.remove(path)
        except OSError:
            pass
        return None
    return data


def _delete_token(token: str) -> None:
    """删除单个 token 文件。"""
    try:
        os.remove(TOKEN_DIR / token)
    except OSError:
        pass


def _clear_all_tokens() -> None:
    """清除所有 token。"""
    try:
        for f in TOKEN_DIR.iterdir():
            try:
                f.unlink()
            except OSError:
                pass
    except FileNotFoundError:
        pass


def _load_auth() -> dict:
    """Load auth data, create or repair default if missing/corrupted."""
    default = {"username": "MisMiss", "password": _hash("MisMiss"), "first_login": True}
    AUTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        if not AUTH_FILE.exists():
            with open(AUTH_FILE, "w", encoding="utf-8") as f:
                json.dump(default, f)
            return default
        with open(AUTH_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict) or "username" not in data or "password" not in data:
            raise ValueError("无效的 auth.json")
        return data
    except (json.JSONDecodeError, ValueError, OSError):
        with open(AUTH_FILE, "w", encoding="utf-8") as f:
            json.dump(default, f)
        return default


def _save_auth(data: dict) -> None:
    with open(AUTH_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def verify_token(token: str) -> str | None:
    """Return username if token is valid, else None."""
    data = _load_token(token)
    if data is None:
        return None
    return data.get("username")


# ---- Middleware helper ----
def require_auth(authorization: str = Header(default="")) -> str:
    """FastAPI dependency: extract and verify Bearer token, return username."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未登录")
    token = authorization[7:]
    username = verify_token(token)
    if not username:
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")
    return username


# ---- Routes ----

@router.post("/auth/login")
async def login(body: dict):
    """Login with username/password. Returns token + first_login flag."""
    username = body.get("username", "").strip()
    password = body.get("password", "")

    auth = _load_auth()
    if username != auth["username"] or _hash(password) != auth["password"]:
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    token = secrets.token_hex(32)
    _save_token(token, username, time.time() + TOKEN_TTL)

    return {
        "token": token,
        "username": username,
        "first_login": auth.get("first_login", False),
    }


@router.post("/auth/change-password")
async def change_password(body: dict):
    """修改用户名和/或密码。"""
    token = body.get("token", "")
    user = verify_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="未登录")

    current = body.get("current_password", "")
    new_username = body.get("new_username", "").strip()
    new_password = body.get("new_password", "").strip()

    auth = _load_auth()
    if auth.get("first_login", False):
        # 首次登录无需验证原密码
        pass
    elif current and _hash(current) != auth["password"]:
        raise HTTPException(status_code=403, detail="当前密码错误")
    elif not current:
        raise HTTPException(status_code=400, detail="请输入当前密码")

    if new_username:
        auth["username"] = new_username
    if new_password and len(new_password) >= 4:
        auth["password"] = _hash(new_password)

    auth["first_login"] = False
    _save_auth(auth)

    # 清除所有 token，强制重新登录
    _clear_all_tokens()

    msg = "已更新，请重新登录"
    if new_username: msg = f"用户名已改为 {new_username}，请重新登录"
    return {"success": True, "message": msg, "username": auth["username"], "relogin": True}


@router.get("/auth/check")
async def check_auth(authorization: str = Header(default="")):
    """验证 token 有效性并返回 first_login 状态。"""
    token = authorization.removeprefix("Bearer ")
    username = verify_token(token) if token else None
    auth = _load_auth()
    return {
        "valid": username is not None,
        "username": auth["username"],
        "first_login": auth.get("first_login", False),
    }


@router.post("/auth/skip-first-login")
async def skip_first_login():
    """跳过首次登录的密码修改提示（标记 first_login=False）。"""
    auth = _load_auth()
    auth["first_login"] = False
    _save_auth(auth)
    return {"success": True, "message": "已跳过首次登录引导"}

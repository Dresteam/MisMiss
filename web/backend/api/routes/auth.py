"""
Simple authentication — username/password stored in data/auth.json.
Password hashed with SHA-256, token-based session in memory.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, Header, Request
from fastapi.responses import JSONResponse

router = APIRouter()

AUTH_FILE = Path(__file__).resolve().parent.parent.parent.parent.parent / "data" / "auth.json"

# In-memory token store: token -> {"username": str, "expires": float}
_tokens: dict[str, dict] = {}
TOKEN_TTL = 30 * 24 * 3600  # 30 days


def _hash(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


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
    entry = _tokens.get(token)
    if not entry:
        return None
    if time.time() > entry["expires"]:
        del _tokens[token]
        return None
    return entry["username"]


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
    _tokens[token] = {"username": username, "expires": time.time() + TOKEN_TTL}

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
    _tokens.clear()

    msg = "已更新，请重新登录"
    if new_username: msg = f"用户名已改为 {new_username}，请重新登录"
    return {"success": True, "message": msg, "username": auth["username"], "relogin": True}


@router.get("/auth/check")
async def check_auth(username: str = Header(default="")):
    """Check if auth is still needed / if this is first login."""
    auth = _load_auth()
    return {
        "username": auth["username"],
        "first_login": auth.get("first_login", False),
    }

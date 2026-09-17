# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for MisMiss standalone executable
# Usage: pyinstaller mismiss.spec

import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH)

a = Analysis(
    [str(ROOT / 'scripts' / 'pyinstaller_entry.py')],
    pathex=[
        str(ROOT / 'src'),
        str(ROOT / 'web' / 'backend'),
    ],
    binaries=[],
    datas=[
        (str(ROOT / 'web' / 'frontend' / 'dist'), 'web/frontend/dist'),
        (str(ROOT / 'config.yml'), '.'),
        (str(ROOT / 'src'), 'src'),
        (str(ROOT / 'web' / 'backend'), 'web/backend'),
        # 更新日志 —— 账户登录后按版本弹出（core.version.load_changelog 读取）
        (str(ROOT / 'docs' / 'changelog'), 'docs/changelog'),
    ],
    hiddenimports=[
        'core', 'core.server', 'core.bot', 'core.bot.mis_bot',
        'core.events', 'core.events.bus',
        'core.livestream', 'core.livestream.mis_livestream',
        'core.network', 'core.network.client',
        'core.network.endpoints',
        'core.plugin', 'core.plugin.plugin_manager', 'core.plugin.config_manager',
        'core.plugin.permission_manager',
        'core.logging', 'core.config', 'core.models',
        'interfaces', 'interfaces.server', 'interfaces.bot', 'interfaces.bot.bot',
        'interfaces.event', 'interfaces.event.event',
        'interfaces.plugin', 'interfaces.plugin.plugin', 'interfaces.plugin.plugin_metadata',
        'uvicorn', 'uvicorn.loops.auto', 'uvicorn.protocols.http.auto',
        'fastapi', 'fastapi.middleware', 'fastapi.middleware.cors',
        'fastapi.staticfiles', 'fastapi.responses',
        'starlette', 'starlette.middleware', 'starlette.middleware.cors',
        'websockets', 'httpx', 'brotli', 'loguru', 'yaml',
        'api', 'api.deps', 'api.schemas',
        'api.routes', 'api.routes.bot', 'api.routes.live', 'api.routes.plugin',
        'api.routes.server', 'api.routes.dashboard', 'api.routes.ws',
        'api.routes.config', 'api.routes.proxy', 'api.routes.auth',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['pip', 'pip._vendor', 'pip._internal'],
    noarchive=False,
)

# Auto-collect submodules for major frameworks
for m in ('fastapi', 'uvicorn', 'starlette', 'websockets', 'httpx', 'pydantic', 'anyio', 'loguru', 'brotli'):
    a.hiddenimports += collect_submodules(m)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='mismiss',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

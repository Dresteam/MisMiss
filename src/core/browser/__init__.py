"""可选的浏览器发送兜底。"""

from .bridge import (
    BrowserBridge,
    BrowserConfig,
    BrowserDisabledError,
    BrowserError,
    BrowserSendResult,
    BrowserUnavailableError,
)

__all__ = [
    "BrowserBridge",
    "BrowserConfig",
    "BrowserDisabledError",
    "BrowserError",
    "BrowserSendResult",
    "BrowserUnavailableError",
]

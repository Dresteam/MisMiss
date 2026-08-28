"""多账户面板 —— 账户管理、公共 Bot、授权码与到期调度。"""

from core.account.manager import AccountManager, AccountRecord
from core.account.license import LicenseStore
from core.account.expiry import ExpiryScheduler
from core.account.migration import migrate_legacy_data

__all__ = [
    "AccountManager",
    "AccountRecord",
    "LicenseStore",
    "ExpiryScheduler",
    "migrate_legacy_data",
]

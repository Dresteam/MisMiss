"""授权码管理 —— 批量生成、兑换、列表与撤销。

授权码存储于 panel.json 的 ``licenses`` 字段,由 :class:`AccountManager`
持有字典并负责持久化,本模块只实现纯逻辑。
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone

from core.exceptions import CoreLicenseException
from core.logging import get_logger

_log = get_logger(__name__)

# 授权码字符集:排除易混淆字符 0 O 1 I L
_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
_CODE_GROUP = 4
_CODE_GROUPS = 3


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _generate_code() -> str:
    """生成形如 ``MM-XXXX-XXXX-XXXX`` 的授权码。"""
    groups = [
        "".join(secrets.choice(_ALPHABET) for _ in range(_CODE_GROUP))
        for _ in range(_CODE_GROUPS)
    ]
    return "MM-" + "-".join(groups)


class LicenseStore:
    """授权码纯逻辑(不负责持久化,由 AccountManager 调用后落盘)。"""

    def __init__(self, licenses: dict[str, dict]) -> None:
        self._licenses = licenses

    @property
    def all(self) -> dict[str, dict]:
        return self._licenses

    def generate(self, count: int, days: int, note: str = "") -> list[str]:
        """批量生成授权码,返回码列表。

        :param count: 生成数量(1~100)
        :param days: 每个码授予的天数
        :param note: 批次备注
        """
        if not (1 <= count <= 100):
            raise CoreLicenseException("生成数量必须在 1~100 之间")
        if days <= 0:
            raise CoreLicenseException("授权天数必须大于 0")
        batch = datetime.now().strftime("%Y%m%d-%H%M%S")
        codes: list[str] = []
        for _ in range(count):
            code = _generate_code()
            while code in self._licenses:
                code = _generate_code()
            self._licenses[code] = {
                "days": int(days),
                "batch": batch,
                "note": note,
                "generated_at": _now_iso(),
                "used_at": None,
                "used_by_account_id": None,
            }
            codes.append(code)
        _log.info("已生成 {} 个授权码 ({} 天, 批次 {})", count, days, batch)
        return codes

    def redeem(self, code: str, account_id: int) -> int:
        """兑换授权码,返回授予天数。

        :raises CoreLicenseException: 码不存在或已被使用
        """
        code = code.strip().upper()
        info = self._licenses.get(code)
        if info is None:
            raise CoreLicenseException(f"授权码 {code} 不存在")
        if info.get("used_at"):
            raise CoreLicenseException(f"授权码 {code} 已被使用")
        info["used_at"] = _now_iso()
        info["used_by_account_id"] = int(account_id)
        _log.info("授权码 {} 已兑换 (账户 {}, {} 天)", code, account_id, info["days"])
        return int(info["days"])

    def revoke(self, code: str) -> None:
        """撤销未使用的授权码。

        :raises CoreLicenseException: 码不存在或已被使用
        """
        code = code.strip().upper()
        info = self._licenses.get(code)
        if info is None:
            raise CoreLicenseException(f"授权码 {code} 不存在")
        if info.get("used_at"):
            raise CoreLicenseException("已使用的授权码不可撤销")
        del self._licenses[code]
        _log.info("授权码已撤销: {}", code)

    def list(self) -> list[dict]:
        """返回全部授权码(按生成时间倒序)。"""
        return sorted(
            ({"code": code, **info} for code, info in self._licenses.items()),
            key=lambda x: x.get("generated_at", ""),
            reverse=True,
        )

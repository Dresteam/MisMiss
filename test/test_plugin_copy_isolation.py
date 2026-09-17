"""插件副本隔离测试(无网络)。

验证账户实际加载的是 ``data/accounts/{id}/installed_plugins/`` 下的源码副本,
而不是插件库 ``plugins/`` 的源码;并验证各账户拿到独立模块对象。

背景:插件模块原先以 ``import plugins.<dir>.<mod>`` 导入,而账户目录下的
``plugins/`` 是**插件数据目录**,``plugins`` 又是命名空间包——于是仓库的
``plugins/`` 被合并进来并抢先命中,账户永远加载插件库源码,副本形同虚设。

运行: .venv/Scripts/python.exe test/test_plugin_copy_isolation.py
"""
import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.account import AccountManager  # noqa: E402

# 含相对导入的插件源码：同时验证包语义(submodule_search_locations)
_MAIN_PY = '''\
from __future__ import annotations

from interfaces.plugin import Plugin

from .helper import HELPER_TAG


class CopyPlugin(Plugin):
    """用于验证副本加载的插件。"""

    async def initialize(self, config) -> None:
        self.tag = HELPER_TAG
'''

_HELPER_PY = 'HELPER_TAG = "{tag}"\n'


def _write_plugin(root: str, name: str, tag: str) -> str:
    """在指定目录下写一个带相对导入的最小插件，返回插件目录。"""
    d = os.path.join(root, name)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "metadata.yaml"), "w", encoding="utf-8") as f:
        f.write(f"name: {name}\ndesc: copy isolation\nauthor: test\nversion: 1.0.0\n")
    with open(os.path.join(d, "main.py"), "w", encoding="utf-8") as f:
        f.write(_MAIN_PY)
    with open(os.path.join(d, "helper.py"), "w", encoding="utf-8") as f:
        f.write(_HELPER_PY.format(tag=tag))
    return d


async def main():
    data = tempfile.mkdtemp(prefix="mismiss-copy-iso-")
    mgr = AccountManager(data_dir=data)
    mgr.load()
    a1 = (await mgr.create_account("a1", username="u1", password="pw12")).id
    a2 = (await mgr.create_account("a2", username="u2", password="pw12")).id

    for aid, tag in ((a1, "copy-A"), (a2, "copy-B")):
        _write_plugin(
            os.path.join(data, "accounts", str(aid), "installed_plugins"),
            "copy_plugin",
            tag,
        )
        srv = mgr.get_server(aid)
        await srv.refresh_plugins()
        await srv.enable_plugin("copy_plugin")

    s1, s2 = mgr.get_server(a1), mgr.get_server(a2)
    m1 = s1._plugin_manager.get_plugin("copy_plugin")
    m2 = s2._plugin_manager.get_plugin("copy_plugin")
    i1, i2 = m1.plugin_instance, m2.plugin_instance
    root1 = os.path.abspath(os.path.join(data, "accounts", str(a1), "installed_plugins"))

    # ---- 1. 加载的是账户自己的副本 ----
    mod1 = sys.modules[type(i1).__module__]
    loaded = os.path.abspath(mod1.__file__ or "")
    assert loaded.startswith(root1 + os.sep), f"FAIL: 未从账户副本加载 → {loaded}"
    print("PASS 1: 加载的是账户自己的副本(而非插件库源码)")

    # ---- 2. 副本内的相对导入可用 ----
    assert i1.tag == "copy-A", f"FAIL: 相对导入失败 tag={getattr(i1, 'tag', None)}"
    assert i2.tag == "copy-B", f"FAIL: 相对导入失败 tag={getattr(i2, 'tag', None)}"
    print("PASS 2: 副本内的相对导入(from .helper import)可用")

    # ---- 3. 各账户独立模块对象，模块级状态不共享 ----
    assert m1.module_path != m2.module_path, "FAIL: 两账户模块名相同，会共享状态"
    assert m1.module is not m2.module, "FAIL: 两账户共享同一模块对象"
    print("PASS 3: 各账户独立模块对象，模块级状态不共享")

    # ---- 4. 卸载后模块缓存被清除（重载能拿到新代码） ----
    name1 = m1.module_path
    await s1.uninstall_plugin("copy_plugin", delete_config=True, delete_data=True)
    assert name1 not in sys.modules, "FAIL: 卸载后模块仍残留在 sys.modules"
    print("PASS 4: 卸载后模块缓存被清除")

    await mgr.shutdown_all()
    print("\n全部通过")


if __name__ == "__main__":
    asyncio.run(main())

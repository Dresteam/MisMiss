"""更新下载的「停止」功能测试（无外部网络）。

覆盖：
- 下载阶段可以取消，任务终止并写入 cancelled 终态
- 已进入 load 等写入阶段时拒绝取消（409）
- 没有任务时拒绝取消
- 异步下载收到停止信号后立即中止，并删除半截文件

运行: .venv/Scripts/python.exe test/test_update_cancel.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "src"))
sys.path.insert(0, os.path.join(_ROOT, "web", "backend"))

from fastapi import HTTPException  # noqa: E402

from api.routes import update as U  # noqa: E402

_passed = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global _passed
    if not cond:
        raise AssertionError(f"FAIL: {label} {detail}")
    _passed += 1
    print(f"PASS {_passed}: {label}")


async def _wait_forever() -> None:
    await asyncio.Event().wait()


async def test_cancel_running() -> None:
    U._update_task = None
    U._cancel_event = None
    U._start_update_task("apply", "9.9.9", _wait_forever)
    task = U._update_task
    check("任务已启动", task is not None and not task.done())
    check("下载阶段允许停止", U.update_cancellable() is True)

    resp = await U.update_cancel()
    check("取消请求成功", resp.success is True)
    # task.cancel() 之后 Task 自身仍会以 CancelledError 结束（协程里已处理完收尾），
    # 这里按「等待结束、不关心异常」处理，重点是终态落盘。
    await asyncio.gather(task, return_exceptions=True)
    state = U._read_apply_progress()
    check("终态为 cancelled", state.get("state") == "cancelled", str(state))
    check("步骤为 cancelled", state.get("step") == "cancelled", str(state))
    check("任务已清空", U._update_task is None and U.update_busy() is False)


async def test_cancel_rejected_late() -> None:
    U._update_task = None
    U._cancel_event = None
    U._start_update_task("apply", "9.9.9", _wait_forever)
    task = U._update_task
    U._set_apply_progress("apply", U._APPLY_RUNNING, "load", "正在导入镜像", "9.9.9")
    check("写入阶段不允许停止", U.update_cancellable() is False)
    try:
        await U.update_cancel()
        raise AssertionError("FAIL: 写入阶段竟然允许取消")
    except HTTPException as e:
        check("写入阶段取消返回 409", e.status_code == 409, str(e.status_code))
    task.cancel()  # type: ignore[union-attr]
    await asyncio.gather(task, return_exceptions=True)  # type: ignore[arg-type]
    check("清理后无残留任务", U._update_task is None)


async def test_cancel_without_task() -> None:
    U._update_task = None
    U._cancel_event = None
    try:
        await U.update_cancel()
        raise AssertionError("FAIL: 没有任务时竟然允许取消")
    except HTTPException as e:
        check("无任务时取消返回 409", e.status_code == 409, str(e.status_code))


async def test_download_stop() -> None:
    """本地慢速 HTTP 源：收到停止信号后不再继续下载，并删掉半截文件。"""
    body_started = asyncio.Event()

    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            await reader.readuntil(b"\r\n\r\n")
            writer.write(
                b"HTTP/1.1 200 OK\r\nContent-Length: 10485760\r\n"
                b"Content-Type: application/octet-stream\r\n\r\n"
            )
            await writer.drain()
            body_started.set()
            for _ in range(500):
                writer.write(b"x" * 65536)
                await writer.drain()
                await asyncio.sleep(0.01)
        except (ConnectionError, asyncio.CancelledError):
            pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    server = await asyncio.start_server(handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    dest = Path(tempfile.mkdtemp(prefix="mismiss-dl-cancel-")) / "partial.bin"
    cancel = asyncio.Event()

    task = asyncio.create_task(
        U._download_asset(
            f"http://127.0.0.1:{port}/pkg.bin",
            dest,
            {"mirror": "", "proxy": ""},
            cancel,
        )
    )
    await asyncio.wait_for(body_started.wait(), timeout=3)
    cancel.set()
    try:
        await task
        raise AssertionError("FAIL: 停止信号后下载仍然完成")
    except U._UpdateCancelled:
        check("下载收到停止信号后中止", True)
    check("半截文件已删除", not dest.exists())

    server.close()
    await server.wait_closed()


async def test_download_progress() -> None:
    """下载进度回调：总大小已知时给出字节数与百分比。"""
    payload = b"x" * 300000

    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            await reader.readuntil(b"\r\n\r\n")
            writer.write(
                f"HTTP/1.1 200 OK\r\nContent-Length: {len(payload)}\r\n"
                f"Content-Type: application/octet-stream\r\n\r\n".encode()
            )
            await writer.drain()
            for i in range(0, len(payload), 65536):
                writer.write(payload[i:i + 65536])
                await writer.drain()
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    server = await asyncio.start_server(handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    dest = Path(tempfile.mkdtemp(prefix="mismiss-dl-progress-")) / "pkg.bin"
    seen: list[tuple[int, int]] = []

    await U._download_asset(
        f"http://127.0.0.1:{port}/pkg.bin",
        dest,
        {"mirror": "", "proxy": ""},
        None,
        lambda done, total: seen.append((done, total)),
    )
    check("进度回调收到总大小", bool(seen) and seen[-1][1] == len(payload), str(seen))
    check("结束时下载量等于总大小", seen[-1][0] == len(payload), str(seen))
    check("落盘文件大小正确", dest.stat().st_size == len(payload))

    # 回调写进 update_state.json 的字段
    U._download_progress_cb("apply", "9.9.9", "pkg.bin")(512, 1024)
    state = U._read_apply_progress()
    check("进度写入 downloaded", state.get("downloaded") == 512, str(state))
    check("进度写入 total", state.get("total") == 1024, str(state))
    check("进度写入 percent", state.get("percent") == 50, str(state))
    check("步骤为 download", state.get("step") == "download", str(state))

    server.close()
    await server.wait_closed()


async def main() -> None:
    state_dir = Path(tempfile.mkdtemp(prefix="mismiss-update-cancel-"))
    U._UPDATE_STATE_FILE = state_dir / "update_state.json"
    await test_cancel_running()
    await test_cancel_rejected_late()
    await test_cancel_without_task()
    await test_download_stop()
    await test_download_progress()
    print("\n全部通过")


if __name__ == "__main__":
    asyncio.run(main())

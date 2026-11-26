# 浏览器发送兜底

猫耳的 `/api/chatroom/message/send` 对部分账号会返回 `code=0` 却不把消息广播到直播间。
纯 HTTP 重放（即使带 Cookie、Origin/Referer、`X-M-DeviceSign`、UUID v1）也可能被
服务端静默丢弃；真实浏览器页面发送则能成功。

本模块用系统 Edge/Chromium 的 CDP 打开直播间页面，执行真实输入框发送，并在发送后
查询直播间历史确认送达。

## 开关

`config.yml`：

```yaml
browser:
  enabled: false          # 默认关闭
  edge_path: ''           # 留空自动探测 Windows Edge / Linux chromium
  headless: true
  max_concurrency: 2      # 同时最多几个发送页面
  timeout_seconds: 45
```

也可用环境变量 `MIS_BROWSER_PATH` 指定浏览器路径。

> Docker 默认不内置浏览器，推荐使用独立 `mismiss-browser` sidecar，或使用宿主
> Edge。主镜像不应为偶尔的兜底膨胀几百 MB。

## 使用

```bash
# 用账户 6 的私有 Cookie
.venv/Scripts/python.exe scripts/browser_send.py \
  --account 6 --room 869230856 --message "dd"

# 直接指定 Cookie
MIS_COOKIE="FM_SESS=..." .venv/Scripts/python.exe scripts/browser_send.py \
  --room 869230856 --message "dd"
```

输出：

```json
{"ok": true, "msg_id": "...", "message": "dd", "reason": ""}
```

## 并发模型

- **一个浏览器进程**；
- 每次发送创建一个独立 `BrowserContext`，Cookie 互不污染；
- `max_concurrency` 限制同时打开的发送页面；
- 同一 `room_id` 加锁串行，避免同一房间重复发送；
- 发送后查历史，查不到返回 `ok=false`。

多人同时使用时，请求会排队，而不是无限开浏览器。建议：

- 2～3 个并发起步；
- 账户多时优先房管权限，不要把所有消息都压到浏览器；
- 每个房间/账户限速；
- 失败退避，避免平台风控。

## 资源参考

| 项目 | 参考值 |
|------|--------|
| 浏览器进程常驻 | 150～300 MB |
| 每个发送页面 | 50～150 MB |
| Docker 完整 Chromium 增量 | 约 +200～300 MB（压缩后） |
| 仅登录/兜底按需启动 | 平时接近 0 |

## 现状

- 已实现：浏览器启动、Cookie 注入、真实 UI 发送、历史校验、并发/房间锁；
- 尚未自动挂进 `MissevanBot` 的消息队列；当前通过 CLI/后续面板接口调用；
- 下一步可接面板 API 或作为 HTTP 发送失败后的低频兜底。

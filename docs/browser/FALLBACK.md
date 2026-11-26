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

> Docker 镜像已内置 Microsoft Edge（体积会明显增加）。如果部署不需要浏览器登录/兜底，
> 仍建议使用裁剪镜像或独立 sidecar；Windows 可直接复用系统 Edge。

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

## 浏览器登录

猫耳没有可用的扫码登录；登录页支持：

- 手机号 + 短信验证码；
- 手机号 + 密码。

账户详情页「获取 Cookie」里新增了「浏览器登录猫耳」：

1. 选择验证码登录 / 密码登录；
2. 输入手机号（密码登录再输入密码）；
3. 验证码登录点击「获取验证码」，收到短信后填入；
4. 登录成功后，后台自动抽取 Cookie 并通过私有 Cookie 流程保存，账户切换为 private。

登录在服务器上的真实 Edge 页面中完成，密码不会落盘；验证码会话保留 5 分钟。
若平台弹滑动验证/CAPTCHA，浏览器登录会失败，需要人工处理（当前不实现绕过）。

## 现状

- 已实现：浏览器启动、Cookie 注入、真实 UI 发送、历史校验、并发/房间锁；
- 尚未自动挂进 `MissevanBot` 的消息队列；当前通过 CLI/后续面板接口调用；
- 下一步可接面板 API 或作为 HTTP 发送失败后的低频兜底。

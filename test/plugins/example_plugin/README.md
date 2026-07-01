# ExamplePlugin

示例插件 —— 演示 MisMiss 插件系统的基本用法。

## 功能

- 监听直播间开播/下播事件
- 监听弹幕消息事件
- 监听礼物赠送事件
- 监听用户进入事件

## 事件处理器

| 方法 | 事件类型 | 说明 |
|------|---------|------|
| `on_open` | `LiveOpenEvent` | 直播间开播 |
| `on_close` | `LiveCloseEvent` | 直播间下播 |
| `on_message` | `LiveMessageEvent` | 弹幕消息 |
| `on_gift` | `LiveGiftEvent` | 赠送礼物 |
| `on_join` | `LiveJoinEvent` | 用户进入 |

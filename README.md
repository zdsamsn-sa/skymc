# SkyMC 自动续期工具 v12

## 新增 NODE_LINK

GitHub Secrets 增加：

| Secret | 必须 | 说明 |
|--------|------|------|
| `SKYMC_EMAIL` | 是 | 登录邮箱 |
| `SKYMC_PASSWORD` | 是 | 登录密码 |
| `TG_BOT_TOKEN` | 推荐 | Telegram Bot Token |
| `TG_CHAT_ID` | 推荐 | Telegram Chat ID |
| `NODE_LINK` | 推荐 | `vless://...` 或 `vmess://...` 节点链接，用于 sing-box 代理突破区域限制 |

设置 `NODE_LINK` 后，脚本会：
1. 解析节点链接
2. 启动本地 sing-box（`127.0.0.1:7890` mixed）
3. 浏览器和 Telegram 请求都走该代理
4. 日志里打印代理后的出口 IP（不会打印节点明文）

未设置 `NODE_LINK` 时行为与 v11.1 相同（直连）。

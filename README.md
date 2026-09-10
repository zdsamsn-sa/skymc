# SkyMC 免费服务器自动续期工具 v3

针对服务器 `TuUzR_dWxO2P`（zdsa.skymc.io）

## 本版本更新

- **新增 Cloudflare「Verify you are human」模拟点击**
  - 自动检测验证框
  - 模拟鼠标移动 + 点击
  - 支持 iframe 内点击
  - 等待验证结果并截图发送到 Telegram
- 隐藏 webdriver 特征，降低被检测概率
- 成功 / 失败都会发送带截图的 Telegram 通知

## 文件说明

| 文件 | 推荐度 | 说明 |
|------|--------|------|
| `skymc_remind.py` | ★★★★★ | 纯提醒 + Telegram（最稳定，推荐） |
| `skymc_renew.py` | ★★★☆☆ | 自动登录 + 模拟点击 Cloudflare + 点击 Renew |
| `.github/workflows/skymc-remind.yml` | 推荐 | 定时提醒 |
| `.github/workflows/skymc-renew.yml` | 实验 | 自动点击（已增强 Cloudflare 处理） |

## 使用方法

### 1. 获取 Telegram 配置

1. 找 `@BotFather` 创建机器人 → 拿到 **Token**
2. 给你的机器人发任意消息
3. 打开：`https://api.telegram.org/bot你的Token/getUpdates`
4. 找到 `"chat":{"id": 数字}` → 这就是 **Chat ID**

### 2. 设置 GitHub Secrets

| Secret 名称 | 是否必须 | 说明 |
|-------------|---------|------|
| `TG_BOT_TOKEN` | 是 | Telegram Bot Token |
| `TG_CHAT_ID` | 是 | 你的 Chat ID |
| `SKYMC_EMAIL` | 仅自动点击需要 | 登录邮箱 |
| `SKYMC_PASSWORD` | 仅自动点击需要 | 登录密码 |

### 3. 上传并运行

把整个文件夹内容推送到 GitHub 仓库即可。

- 提醒方案默认每 **6 小时**运行一次
- 自动点击方案默认每 **8 小时**运行一次

## 注意事项

1. Cloudflare 验证越来越严格，即使加了模拟点击，**成功率仍然无法保证 100%**。
2. 如果自动点击连续失败，请优先使用提醒方案，手动点一次 Renew 即可。
3. 建议把提醒和自动点击同时启用，互为备份。
4. 账号密码务必使用 Secrets，不要写在代码里。

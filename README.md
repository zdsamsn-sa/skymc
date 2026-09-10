# SkyMC 免费服务器自动续期工具 v5

## 本版本修复

- **修复邮箱输入框找不到的问题**（针对 "Username or Email Address" 字段）
- 增加更多选择器 + JS 兜底填写
- 保留 SeleniumBase UC 模式 + `uc_gui_click_captcha()` 处理 Cloudflare
- 登录/续期全过程截图 + Telegram 通知

## 使用方法

### Secrets 配置

| Secret | 说明 |
|--------|------|
| `SKYMC_EMAIL` | 登录邮箱 |
| `SKYMC_PASSWORD` | 登录密码 |
| `TG_BOT_TOKEN` | Telegram Bot Token（推荐） |
| `TG_CHAT_ID` | Telegram Chat ID（推荐） |

### 上传后

1. 先在 Actions 页面手动触发一次测试
2. 查看日志和上传的截图确认是否成功
3. 成功后可依赖定时任务自动运行

## 文件说明

- `skymc_renew.py`：主自动续期脚本
- `skymc_remind.py`：纯提醒备用方案（100% 稳定）
- `.github/workflows/`：两个工作流

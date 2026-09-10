# SkyMC 免费服务器自动续期工具 v4

参考 therose.py，使用 **SeleniumBase UC 模式 + `uc_gui_click_captcha()`** 处理 Cloudflare Turnstile。

## 核心改进

- 使用 `seleniumbase` 的 `uc=True`（undetected-chromedriver）
- 调用 `sb.uc_gui_click_captcha()` 专门处理 Turnstile 验证
- GitHub Actions 中配合 **Xvfb 虚拟显示**，让 GUI 点击能正常工作
- 成功/失败都会发送带截图的 Telegram 通知

## 文件说明

| 文件 | 说明 |
|------|------|
| `skymc_renew.py` | 主脚本（自动登录 + 处理验证 + 点击 Renew） |
| `skymc_remind.py` | 纯提醒脚本（备用，100% 稳定） |
| `.github/workflows/skymc-renew.yml` | 自动续期工作流（含 Xvfb） |
| `.github/workflows/skymc-remind.yml` | 提醒工作流 |

## 使用方法

### 1. 设置 Secrets

| Secret | 必须 | 说明 |
|--------|------|------|
| `SKYMC_EMAIL` | 是 | 登录邮箱 |
| `SKYMC_PASSWORD` | 是 | 登录密码 |
| `TG_BOT_TOKEN` | 推荐 | Telegram Bot Token |
| `TG_CHAT_ID` | 推荐 | Telegram Chat ID |

### 2. 上传代码

把本文件夹内容推送到 GitHub 仓库即可。

### 3. 本地测试（推荐先测）

```bash
pip install -r requirements.txt

export SKYMC_EMAIL="你的邮箱"
export SKYMC_PASSWORD="你的密码"
export TG_BOT_TOKEN="可选"
export TG_CHAT_ID="可选"

# 本地直接运行（有图形界面时效果最好）
python skymc_renew.py
```

## 注意事项

1. `uc_gui_click_captcha()` 需要图形环境，GitHub Actions 已通过 Xvfb 解决。
2. 即使使用了 UC 模式，Cloudflare 仍可能偶尔拦截，因此保留了提醒方案作为备份。
3. 建议同时启用两个工作流：
   - 自动续期每 8 小时尝试一次
   - 提醒每 6 小时发一次，确保不会漏掉
4. 如果连续失败，请检查 Actions 日志和上传的截图。

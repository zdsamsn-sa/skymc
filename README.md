# SkyMC 自动续期工具 v7

## 本次重点改进
- 在**打开页面后、填写完成后、点击登录后**三个时机都检测并处理 Cloudflare
- `handle_cloudflare` 增加多次重试 + 多种点击方式
- 登录循环中持续检测验证弹窗

## 现实说明
即使使用 SeleniumBase UC + `uc_gui_click_captcha`，在 GitHub Actions 的 Xvfb 环境下，Cloudflare Turnstile 仍有一定概率无法通过。

**强烈建议同时启用提醒工作流作为保底。**

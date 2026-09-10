# SkyMC 自动续期工具 v8

## 本次修复
1. 修复 JS `Identifier 'selectors' has already been declared` 语法错误
2. 点击 Renew 后再次处理可能弹出的 Cloudflare
3. 点击后会再尝试点一次 Renew，防止被验证打断
4. 最终截图用于确认倒计时是否重置

## 说明
从 v7 日志看，登录和点击 Renew 已经成功。v8 主要解决面板页再次弹出验证的问题。

# SkyMC 自动续期工具 v10

## 本次关键修复（根据失败日志里的真实 HTML）

登录页实际输入框：

| 字段 | id | name | type | placeholder |
|------|-----|------|------|-------------|
| 邮箱 | `usernameOrEmail-s1` | `identifier` | text | 空 |
| 密码 | `password-s1` | `password` | password | 空 |

之前脚本一直在找 `placeholder*="Email"`、`input[type="email"]`、`name=email`，全部对不上。

另外 `is_element_visible(sel, timeout=1)` 在 SeleniumBase 里 **没有 timeout 参数**，会抛异常被 `except` 吃掉，所以循环 25 秒都填不进去。

## v10 改动

- 使用真实选择器：`#usernameOrEmail-s1` / `input[name="identifier"]`
- 用 `wait_for_element_visible` + `type` 填写
- JS 用 `arguments` 传值，不再拼进字符串
- Cloudflare 只在出现 **Verify you are human** 文案时才处理，不再因为页面里有 turnstile 脚本就误判
- 使用 `uc_open_with_reconnect` 打开登录页

## Secrets

- `SKYMC_EMAIL`
- `SKYMC_PASSWORD`
- `TG_BOT_TOKEN`（推荐）
- `TG_CHAT_ID`（推荐）

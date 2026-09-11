# SkyMC 免费服务器自动续期工具

针对 SkyMC 免费计划服务器的 GitHub Actions 自动续期方案。

- 面板：https://skymc.org/en/server/*****
- 登录：https://skymc.org/en/login
- 游戏地址：`***.skymc.io`

免费计划需要定期点面板上的蓝色 **Renew** 按钮，倒计时归零后服务器会停止。本工具用 GitHub Actions 定时登录、过 Cloudflare、点 Renew；关机则点 Start；并把结果（含倒计时和截图）发到 Telegram。

---

## 功能一览

| 功能 | 说明 |
|------|------|
| 自动登录 | 填写邮箱/密码，点击 Login |
| Cloudflare Turnstile | SeleniumBase UC 模式 + `uc_gui_click_captcha()` |
| 自动续期 | 进入面板点击 **Renew** |
| 关机启动 | 状态不是 Online 时点击 **Start / 启动** |
| 倒计时读取 | 续期前/后读取 `MM:SS`（分钟:秒）并对比 |
| 干净截图 | 等验证弹窗消失后再截图，上传 Actions Artifact |
| Telegram 通知 | 文字 + 截图 |
| 节点代理 | `NODE_LINK`（`vless://` / `vmess://`）启动 sing-box 突破区域限制 |

---

## 目录结构

```
skymc-renew/
├── README.md
├── requirements.txt
├── skymc_renew.py                 # 主脚本（登录 / 验证 / 续期 / 启动 / 代理）
├── skymc_remind.py                # 纯提醒脚本（不登录）
└── .github/workflows/
    ├── skymc-renew.yml            # 每 8 小时自动续期
    └── skymc-remind.yml           # 每 6 小时提醒
```

依赖：

```
seleniumbase>=4.20.0
requests>=2.28.0
```

---

## 工作流程（skymc_renew.py）

1. 若配置了 `NODE_LINK`：解析节点 → 启动 sing-box（`127.0.0.1:7890`）→ 浏览器和 HTTP 走 SOCKS5
2. 查询出口 IP
3. 打开 https://skymc.org/en/login（`uc_open_with_reconnect`）
4. 处理 Cloudflare「Verify you are human」
5. 填写邮箱 `#usernameOrEmail-s1`（`name=identifier`）
6. 填写密码 `#password-s1`（`name=password`）
7. 点击 Login，必要时再次过验证
8. 打开服务器面板
9. 读取状态（Online / Offline）和剩余时间
10. 若已关机：点击 Start，等待上线
11. 点击 Renew；若弹出验证，处理后可再点一次
12. 再读一次剩余时间，对比是否增加
13. 等验证框消失后截图 `final_result.png`
14. 发送 Telegram 通知（带图）

倒计时格式为 **分钟:秒**，不是小时。

- `102:18` = 102 分钟 18 秒
- `119:47` = 119 分钟 47 秒
- 差值 `1049` = 1049 秒

Telegram 示例：

```
【SkyMC 续期】
✅ 续期已执行
服务器: TuUzR_dWxO2P
当前状态: Online
启动操作: 已在运行
续期前时间: 102:18（102分钟18秒）
续期后时间: 119:47（119分钟47秒）
结论: 倒计时已增加约 1049 秒，续期生效
IP: x.x.x.x
```

---

## 登录页真实选择器

由失败日志确认：

| 字段 | id | name | type | placeholder |
|------|-----|------|------|-------------|
| 邮箱 | `usernameOrEmail-s1` | `identifier` | text | 空 |
| 密码 | `password-s1` | `password` | password | 空 |

不要用 `input[type="email"]` 或 `placeholder*="Email"`，页面上不存在。

---

## GitHub Secrets（必须配置）

仓库 → **Settings → Secrets and variables → Actions → New repository secret**

| Secret 名称 | 必须 | 说明 |
|-------------|------|------|
| `SKYMC_EMAIL` | 是 | 登录邮箱 |
| `SKYMC_PASSWORD` | 是 | 登录密码 |
| `TG_BOT_TOKEN` | 强烈建议 | Telegram 机器人 Token |
| `TG_CHAT_ID` | 强烈建议 | Telegram Chat ID |
| `NODE_LINK` | 建议 | `vless://...` 或 `vmess://...`，用于代理 |

兼容别名（一般不用配）：`EMAIL`、`PASSWORD` 可代替 `SKYMC_EMAIL` / `SKYMC_PASSWORD`。

### 脚本还支持、工作流默认未传入

| 变量 | 默认 | 说明 |
|------|------|------|
| `SERVER_URL` | `https://skymc.org/en/server/TuUzR_dWxO2P` | 面板地址 |
| `IS_PROXY` | `false` | 强制使用 `PROXY_SERVER`（有 `NODE_LINK` 时会自动改为 true） |
| `PROXY_SERVER` | `socks5://127.0.0.1:7890` | 已有本地代理时可直接填 |
| `SINGBOX_PORT` | `7890` | sing-box 本地 mixed 端口 |

需要换服务器或自定义代理时，在 `.github/workflows/skymc-renew.yml` 的 `env:` 里加上即可。

---

## 配置 Telegram

1. Telegram 找 [@BotFather](https://t.me/BotFather)，`/newbot` 拿到 Token
2. 给你的机器人发任意一条消息
3. 浏览器打开：`https://api.telegram.org/bot<Token>/getUpdates`
4. 找到 `"chat":{"id": 数字}`，这就是 `TG_CHAT_ID`
5. 把 Token 和 Chat ID 填进 GitHub Secrets

未配置时脚本仍会跑完，只是日志提示「跳过通知」。

---

## 配置 NODE_LINK（sing-box 代理）

用于 GitHub Actions IP 被 Cloudflare / 区域限制拦截时。

1. Secrets 新增 `NODE_LINK`，值为完整分享链接，例如：
   - `vless://uuid@host:443?type=tcp&security=reality&pbk=...&sid=...&sni=...&fp=chrome&flow=xtls-rprx-vision#name`
   - `vmess://` + Base64 JSON
2. 工作流会安装 sing-box `1.11.15`
3. 脚本解析链接，启动本地 mixed 入站 `127.0.0.1:7890`
4. Selenium 与 requests 都走 `socks5://127.0.0.1:7890`
5. 日志只打印协议类型和出口 IP，**不会打印节点明文**

支持：

- `vless://`：tcp / ws / grpc / httpupgrade；tls / reality
- `vmess://`：tcp / ws / grpc；可选 tls

不填 `NODE_LINK` 则直连。填了但 sing-box 启动失败，脚本会退出（避免在错误出口上硬跑）。

---

## 部署到 GitHub

1. 新建一个 **Private** 仓库（账号密码不要放公开库）
2. 把本目录全部文件推上去（保留 `.github/workflows/`）
3. 配置 Secrets
4. 打开 **Actions**，分别启用两个工作流
5. 先手动 **Run workflow** 测一次自动续期
6. 查看日志和 Artifact `renew-screenshots`

### 定时

| 工作流 | Cron（UTC） | 大约频率 |
|--------|-------------|----------|
| `skymc-renew.yml` | `0 */8 * * *` | 每 8 小时续期 |
| `skymc-remind.yml` | `0 */6 * * *` | 每 6 小时提醒 |

建议两个都开：自动续期为主，提醒保底。

修改频率示例：

```yaml
- cron: '0 */1 * * *'      # 每 1 小时
```

---

## 本地运行

需要图形界面（或自己配 xvfb），以及 Chrome。

```bash
pip install -r requirements.txt

export SKYMC_EMAIL="你的邮箱"
export SKYMC_PASSWORD="你的密码"
export TG_BOT_TOKEN="可选"
export TG_CHAT_ID="可选"
# export NODE_LINK="vless://..."   # 可选；本机还要安装 sing-box

python skymc_renew.py
```

纯提醒：

```bash
export TG_BOT_TOKEN="..."
export TG_CHAT_ID="..."
python skymc_remind.py
```

---

## 截图与产物

| 文件 | 何时生成 |
|------|----------|
| `login_failed.png` | 登录失败 |
| `renew_not_found.png` | 未找到 Renew |
| `final_result.png` | 流程结束（尽量在验证框消失后） |

GitHub Actions 无论成功失败都会上传 `*.png` 到 Artifact：`renew-screenshots`。

---

## 常见问题

**登录页找不到输入框**  
必须用 `#usernameOrEmail-s1` / `input[name="identifier"]`，不要用 email placeholder。

**卡在 Verify you are human**  
GitHub 出口 IP 容易被 Cloudflare 拦。配置 `NODE_LINK` 换出口。UC 模式也不能保证 100% 过验证。

**续期显示成功但倒计时没变**  
看「续期前/后时间」。变化很小可能刚续过；截图仍有验证框时，以倒计时数字为准。

**时间被写成小时**  
已按面板实际格式改为分钟:秒。`102:18` = 102 分钟 18 秒。

**Telegram 没收到**  
检查 `TG_BOT_TOKEN`、`TG_CHAT_ID` 是否加在仓库 Secrets 里。日志若有「未配置」就是没注入成功。

**NODE_LINK 无效**  
目前只认 `vless://` 和 `vmess://`。解析失败或 sing-box 起不来会直接退出，日志在 `/tmp/sing-box-skymc.log`（Actions 里会打印末尾）。

**服务器是 Offline**  
脚本会点 Start，最多等待一段时间确认 Online，然后再 Renew。

---

## 安全注意

- 仓库务必 **Private**
- 账号、密码、节点链接只放 Secrets，不要写进代码
- 日志不会打印密码和 NODE_LINK 全文
- 不要把 `final_result.png` 发到公开地方（可能含面板信息）

---

## 提醒脚本文案（skymc_remind.py）

```
SkyMC 免费服务器续期提醒

服务器：***
ID：*****
地址：***.skymc.io

面板：https://skymc.org/en/server/****

请尽快登录并点击蓝色 Renew 按钮！
```

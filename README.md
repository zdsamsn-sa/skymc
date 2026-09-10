# SkyMC 免费服务器自动续期工具

针对服务器 `TuUzR_dWxO2P`（zdsa.skymc.io）的完整自动续期方案。

## 文件说明

| 文件 | 说明 |
|------|------|
| `skymc_renew.py` | 核心 Python 脚本（使用 Playwright 自动登录并点击 Renew） |
| `.github/workflows/skymc-renew.yml` | GitHub Actions 工作流（定时自动运行） |
| `requirements.txt` | Python 依赖 |
| `README.md` | 本说明文件 |

## 一、本地运行（推荐先测试）

1. 安装依赖：
```bash
pip install -r requirements.txt
playwright install chromium
```

2. 设置账号密码（二选一）：

**方法 A：环境变量（推荐）**
```bash
export SKYMC_EMAIL="你的登录邮箱"
export SKYMC_PASSWORD="你的登录密码"
python skymc_renew.py
```

**方法 B：直接修改脚本**
打开 `skymc_renew.py`，修改开头的 `EMAIL` 和 `PASSWORD` 两行。

3. 运行后会自动登录并点击 Renew 按钮，同时保存截图。

## 二、GitHub Actions 自动运行

1. 把整个文件夹内容上传到你的 GitHub 仓库（保持目录结构）。

2. 在仓库设置 Secrets：
   - 进入仓库 → **Settings** → **Secrets and variables** → **Actions**
   - 点击 **New repository secret**
   - 添加两个：
     - 名称：`SKYMC_EMAIL`，值：你的登录邮箱
     - 名称：`SKYMC_PASSWORD`，值：你的登录密码

3. 提交代码后，Actions 会自动按计划运行（默认每 6 小时一次）。

4. 也可在 Actions 页面手动点击 **Run workflow** 立即执行。

5. 运行结束后可在 Artifacts 下载截图查看结果。

## 三、调整运行频率

编辑 `.github/workflows/skymc-renew.yml` 中的 cron 表达式：

```yaml
- cron: '0 */6 * * *'   # 每 6 小时
- cron: '0 */4 * * *'   # 每 4 小时
- cron: '0 8,20 * * *'  # 每天 8 点和 20 点
```

## 四、注意事项

- 免费计划需要定期点击 **Renew**，否则倒计时结束后服务器会停止。
- 建议频率：每 4~8 小时运行一次（根据面板显示的剩余时间调整）。
- 账号密码请务必使用 GitHub Secrets，不要硬编码在代码中。
- 如果网站前端结构发生变化，脚本可能需要更新选择器。
- 本工具仅供个人学习使用，请遵守网站服务条款。

## 五、常见问题

**Q：提示找不到 Renew 按钮？**  
A：可能刚刚已经续期过，或服务器未启动。先手动登录面板确认状态。

**Q：登录失败？**  
A：检查邮箱密码是否正确，或网站是否开启了额外验证。

**Q：想收到手机通知？**  
A：可自行在脚本末尾添加 Telegram / 企业微信 / Discord webhook 代码。

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SkyMC 免费服务器续期提醒脚本（推荐使用）
功能：定时提醒 + Telegram 通知（带截图说明）
不会触发 Cloudflare 验证，稳定可靠
"""

import os
import sys
import requests
from datetime import datetime, timezone, timedelta

# ==================== 配置区域 ====================
SERVER_NAME = "zdsa"
SERVER_ID = "TuUzR_dWxO2P"
SERVER_URL = "https://skymc.org/en/server/TuUzR_dWxO2P"
SERVER_ADDRESS = "zdsa.skymc.io"

TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "")
TG_CHAT_ID = os.getenv("TG_CHAT_ID", "")
# =================================================


def send_telegram(text: str, parse_mode: str = "HTML"):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        print("⚠️  未配置 TG_BOT_TOKEN 或 TG_CHAT_ID，跳过 Telegram 通知")
        return False

    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TG_CHAT_ID,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True
    }
    try:
        resp = requests.post(url, json=payload, timeout=15)
        if resp.status_code == 200:
            print("✅ Telegram 通知发送成功")
            return True
        else:
            print(f"❌ Telegram 发送失败: {resp.status_code} - {resp.text}")
            return False
    except Exception as e:
        print(f"❌ Telegram 发送异常: {e}")
        return False


def main():
    bj_tz = timezone(timedelta(hours=8))
    now = datetime.now(bj_tz).strftime("%Y-%m-%d %H:%M:%S")

    print("=" * 50)
    print("SkyMC 免费服务器续期提醒")
    print(f"时间：{now} (北京时间)")
    print("=" * 50)

    message = f"""🔔 <b>SkyMC 免费服务器续期提醒</b>

服务器名称：<code>{SERVER_NAME}</code>
服务器 ID：<code>{SERVER_ID}</code>
服务器地址：<code>{SERVER_ADDRESS}</code>

面板地址：
{SERVER_URL}

请尽快登录面板，点击蓝色的 <b>Renew</b> 按钮！

建议每 4~8 小时操作一次，避免倒计时归零导致服务器停止。

时间：{now}"""

    print(message.replace("<b>", "").replace("</b>", "").replace("<code>", "").replace("</code>", ""))
    print("=" * 50)

    send_telegram(message)
    print("提醒脚本执行完毕")


if __name__ == "__main__":
    main()

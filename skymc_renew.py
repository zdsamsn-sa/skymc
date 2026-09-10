#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SkyMC 免费服务器自动续期脚本 v4
参考 therose.py，使用 SeleniumBase UC 模式 + uc_gui_click_captcha 处理 Cloudflare Turnstile
"""

import os
import sys
import time
import requests
from seleniumbase import SB

# ==================== 配置区域 ====================
EMAIL = os.environ.get("SKYMC_EMAIL") or os.environ.get("EMAIL") or ""
PASSWORD = os.environ.get("SKYMC_PASSWORD") or os.environ.get("PASSWORD") or ""
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN") or ""
TG_CHAT_ID = os.environ.get("TG_CHAT_ID") or ""

SERVER_URL = os.environ.get("SERVER_URL") or "https://skymc.org/en/server/TuUzR_dWxO2P"
LOGIN_URL = "https://skymc.org/en/login"

# 是否使用代理
IS_PROXY = os.environ.get("IS_PROXY", "false").lower() == "true"
PROXY_SERVER = os.environ.get("PROXY_SERVER") or "socks5://127.0.0.1:1080"
REQUESTS_PROXIES = {"http": PROXY_SERVER, "https": PROXY_SERVER} if IS_PROXY else None
# =================================================


def send_tg(token, chat_id, message, image_path=None):
    """发送 Telegram 通知（支持图片）"""
    if not token or not chat_id:
        print("⚠️  未配置 TG_BOT_TOKEN 或 TG_CHAT_ID，跳过通知")
        return

    message = f"【SkyMC 续期】\n{message}"

    if image_path and os.path.exists(image_path):
        url = f"https://api.telegram.org/bot{token}/sendPhoto"
        try:
            with open(image_path, "rb") as f:
                resp = requests.post(
                    url,
                    data={"chat_id": chat_id, "caption": message},
                    files={"photo": f},
                    timeout=20,
                    proxies=REQUESTS_PROXIES,
                )
            if resp.status_code == 200:
                print(f"📨 Telegram 通知已发送（附带图片）")
                return
            else:
                print(f"⚠️ 带图发送失败，回退纯文字: {resp.text}")
        except Exception as e:
            print(f"⚠️ 带图发送异常，回退纯文字: {e}")

    # 纯文字回退
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        resp = requests.post(
            url,
            json={"chat_id": chat_id, "text": message},
            timeout=10,
            proxies=REQUESTS_PROXIES,
        )
        if resp.status_code == 200:
            print("📨 Telegram 通知已发送（纯文字）")
        else:
            print(f"❌ Telegram 发送失败: {resp.text}")
    except Exception as e:
        print(f"❌ Telegram 发送异常: {e}")


def get_current_ip():
    try:
        resp = requests.get("https://api.ip.sb/ip", proxies=REQUESTS_PROXIES, timeout=10)
        if resp.status_code == 200:
            return resp.text.strip()
    except:
        pass
    return "获取失败"


def login(sb, email, password):
    """登录流程（重点处理 Cloudflare Turnstile）"""
    print("🌐 打开登录页面...")
    sb.open(LOGIN_URL)
    sb.wait_for_ready_state_complete()
    time.sleep(2)

    # 检测是否出现 Cloudflare 验证
    page_source = sb.get_page_source().lower()
    if "security verification" in page_source or "verify you are human" in page_source or "cf-turnstile" in page_source:
        print("🛡  检测到 Cloudflare Turnstile，尝试自动处理...")
        try:
            # 核心方法：使用 SeleniumBase 的 UC GUI 点击验证
            sb.uc_gui_click_captcha()
            print("✅ uc_gui_click_captcha 已执行")
            time.sleep(3)
        except Exception as e:
            print(f"⚠️ uc_gui_click_captcha 执行异常: {e}")
            # 备用：尝试普通点击
            try:
                sb.uc_click('input[type="checkbox"]', timeout=5)
                print("✅ 备用 checkbox 点击已执行")
                time.sleep(2)
            except:
                pass

    print("📧 填写邮箱...")
    # 尝试多种选择器
    email_filled = False
    for sel in ['input[type="email"]', 'input[name="email"]', 'input[placeholder*="Email" i]', 'input[placeholder*="Username" i]', 'input[type="text"]']:
        try:
            if sb.is_element_visible(sel, timeout=3):
                sb.type(sel, email, timeout=8)
                email_filled = True
                print(f"   使用选择器: {sel}")
                break
        except:
            continue
    if not email_filled:
        print("❌ 无法找到邮箱输入框")
        sb.save_screenshot("login_failed.png")
        return False

    print("🔑 填写密码...")
    try:
        sb.type('input[type="password"]', password, timeout=8)
    except Exception as e:
        print(f"❌ 填写密码失败: {e}")
        sb.save_screenshot("login_failed.png")
        return False

    time.sleep(1)

    # 再次检查是否有验证（有时验证出现在填完账号后）
    page_source = sb.get_page_source().lower()
    if "verify you are human" in page_source or "security verification" in page_source:
        print("🛡  再次检测到验证，尝试处理...")
        try:
            sb.uc_gui_click_captcha()
            print("✅ 第二次验证处理完成")
            time.sleep(3)
        except Exception as e:
            print(f"⚠️ 第二次验证处理异常: {e}")

    print("⏳ 等待验证 token 生效...")
    time.sleep(2)

    # 点击登录（带重试）
    for attempt in range(3):
        print(f"🔑 点击登录按钮...(第 {attempt + 1} 次)")
        try:
            sb.uc_click('button:contains("Login")')
        except:
            try:
                sb.uc_click('button[type="submit"]')
            except Exception as e:
                print(f"⚠️ 点击登录异常: {e}")

        # 等待跳转
        for _ in range(8):
            current_url = sb.get_current_url()
            if "login" not in current_url.lower() and "skymc.org" in current_url:
                print(f"✅ 登录成功，当前页面: {current_url}")
                return True
            time.sleep(1)

        # 检查错误提示
        try:
            for sel in ['.alert-danger', 'div[role="alert"]', '.text-danger', '.error']:
                if sb.is_element_visible(sel, timeout=1):
                    err_text = sb.get_text(sel)
                    print(f"❌ 登录错误提示: {err_text}")
        except:
            pass

        print("⚠️ 未跳转成功，准备重试...")

    print(f"❌ 登录失败，当前 URL: {sb.get_current_url()}")
    sb.save_screenshot("login_failed.png")
    return False


def click_renew(sb):
    """点击 Renew 按钮"""
    print("📄 进入服务器面板...")
    sb.open(SERVER_URL)
    sb.wait_for_ready_state_complete()
    time.sleep(3)

    print("🔍 查找 Renew 按钮...")
    renew_selectors = [
        'button:contains("Renew")',
        'button:contains("续期")',
        'button >> text=/Renew/i',
        '//button[contains(text(),"Renew")]',
    ]

    for sel in renew_selectors:
        try:
            if sb.is_element_visible(sel, timeout=4):
                print(f"✅ 找到 Renew 按钮: {sel}")
                sb.uc_click(sel)
                print("✅ 已点击 Renew")
                time.sleep(3)
                return True
        except:
            continue

    # JS 兜底
    try:
        result = sb.execute_script("""
            const buttons = document.querySelectorAll('button');
            for (let btn of buttons) {
                const text = (btn.innerText || btn.textContent || '').toLowerCase();
                if (text.includes('renew') || text.includes('续期')) {
                    btn.click();
                    return true;
                }
            }
            return false;
        """)
        if result:
            print("✅ 通过 JavaScript 点击 Renew 成功")
            time.sleep(3)
            return True
    except Exception as e:
        print(f"⚠️ JS 点击失败: {e}")

    print("❌ 未找到 Renew 按钮")
    sb.save_screenshot("renew_not_found.png")
    return False


def main():
    if not EMAIL or not PASSWORD:
        print("❌ 请设置环境变量 SKYMC_EMAIL 和 SKYMC_PASSWORD")
        sys.exit(1)

    print("🚀 启动 SkyMC 自动续期脚本 v4 (SeleniumBase UC 模式)")
    print(f"目标服务器: {SERVER_URL}")

    current_ip = get_current_ip()
    print(f"🎯 当前出口 IP: {current_ip}")

    # UC 模式 + 非无头（验证需要可视化环境）
    # 在 GitHub Actions 上配合 xvfb 使用
    sb_kwargs = {
        "uc": True,           # 关键 undetected-chromedriver
        "headless": False,    # 必须 False，uc_gui_click_captcha 需要 GUI
        "locale_code": "en",
    }
    if IS_PROXY:
        sb_kwargs["proxy"] = PROXY_SERVER
        print(f"⚙️ 已启用代理: {PROXY_SERVER}")

    with SB(**sb_kwargs) as sb:
        # 1. 登录
        success = login(sb, EMAIL, PASSWORD)
        if not success:
            msg = f"❌ 登录失败\nIP: {current_ip}\n请检查账号密码或 Cloudflare 验证情况"
            print(msg)
            send_tg(TG_BOT_TOKEN, TG_CHAT_ID, msg, image_path="login_failed.png")
            return

        # 2. 点击 Renew
        print("\n📄 开始续期流程...")
        renew_ok = click_renew(sb)

        if renew_ok:
            sb.save_screenshot("renew_success.png")
            msg = f"✅ 续期成功！已点击 Renew 按钮\n服务器: TuUzR_dWxO2P\nIP: {current_ip}"
            send_tg(TG_BOT_TOKEN, TG_CHAT_ID, msg, image_path="renew_success.png")
            print(msg)
        else:
            msg = f"❌ 续期失败，未找到 Renew 按钮\n可能刚续期过或页面结构变化\nIP: {current_ip}"
            send_tg(TG_BOT_TOKEN, TG_CHAT_ID, msg, image_path="renew_not_found.png")
            print(msg)

        # 最终状态截图
        final_img = "final_result.png"
        sb.save_screenshot(final_img)
        print(f"📸 最终截图已保存: {final_img}")

    print("🏁 脚本执行完毕")


if __name__ == "__main__":
    main()

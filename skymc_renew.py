#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SkyMC 免费服务器自动续期脚本 v5
修复：邮箱/密码输入框选择器 + 增强稳定性
参考 therose.py 使用 SeleniumBase UC 模式处理 Cloudflare Turnstile
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

IS_PROXY = os.environ.get("IS_PROXY", "false").lower() == "true"
PROXY_SERVER = os.environ.get("PROXY_SERVER") or "socks5://127.0.0.1:1080"
REQUESTS_PROXIES = {"http": PROXY_SERVER, "https": PROXY_SERVER} if IS_PROXY else None
# =================================================


def send_tg(token, chat_id, message, image_path=None):
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
                print("📨 Telegram 通知已发送（附带图片）")
                return
            print(f"⚠️ 带图发送失败，回退纯文字: {resp.text}")
        except Exception as e:
            print(f"⚠️ 带图发送异常，回退纯文字: {e}")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        resp = requests.post(url, json={"chat_id": chat_id, "text": message}, timeout=10, proxies=REQUESTS_PROXIES)
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


def handle_cloudflare(sb):
    """处理 Cloudflare Turnstile 验证"""
    page_source = sb.get_page_source().lower()
    if any(k in page_source for k in ["security verification", "verify you are human", "cf-turnstile", "turnstile"]):
        print("🛡  检测到 Cloudflare Turnstile，尝试自动处理...")
        try:
            sb.uc_gui_click_captcha()
            print("✅ uc_gui_click_captcha 已执行")
            time.sleep(4)
            return True
        except Exception as e:
            print(f"⚠️ uc_gui_click_captcha 异常: {e}")
            # 备用点击
            try:
                sb.uc_click('input[type="checkbox"]', timeout=5)
                print("✅ 备用 checkbox 点击完成")
                time.sleep(3)
                return True
            except:
                pass
            return False
    return True  # 没有验证也返回 True


def login(sb, email, password):
    print("🌐 打开登录页面...")
    sb.open(LOGIN_URL)
    sb.wait_for_ready_state_complete()
    time.sleep(3)

    # 先处理可能出现的 Cloudflare
    handle_cloudflare(sb)
    time.sleep(1)

    print("📧 填写邮箱/用户名...")
    # 更全面的选择器（根据实际页面 "Username or Email Address"）
    email_selectors = [
        'input[placeholder*="Username or Email" i]',
        'input[placeholder*="Email" i]',
        'input[placeholder*="Username" i]',
        'input[type="email"]',
        'input[name="email"]',
        'input[name="username"]',
        'input[type="text"]',
        'form input[type="text"]',
        'form input:not([type="password"]):not([type="hidden"]):not([type="submit"])',
    ]

    email_filled = False
    for sel in email_selectors:
        try:
            if sb.is_element_visible(sel, timeout=3):
                sb.clear(sel)
                sb.type(sel, email, timeout=8)
                email_filled = True
                print(f"   ✅ 邮箱已填写，选择器: {sel}")
                break
        except Exception as e:
            continue

    if not email_filled:
        # 最后手段：用 JS 找第一个可见的文本输入框
        try:
            print("   尝试 JS 方式填写邮箱...")
            sb.execute_script(f"""
                const inputs = document.querySelectorAll('input');
                for (let input of inputs) {{
                    const type = (input.type || '').toLowerCase();
                    if (type !== 'password' && type !== 'hidden' && type !== 'submit' && type !== 'checkbox' && type !== 'radio') {{
                        if (input.offsetParent !== null) {{  // 可见
                            input.value = '{email}';
                            input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                            input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                            return true;
                        }}
                    }}
                }}
                return false;
            """)
            email_filled = True
            print("   ✅ 通过 JS 填写邮箱")
        except Exception as e:
            print(f"   JS 填写失败: {e}")

    if not email_filled:
        print("❌ 无法找到邮箱输入框")
        sb.save_screenshot("login_failed.png")
        # 打印页面部分源码帮助调试
        try:
            src = sb.get_page_source()[:2000]
            print("页面源码片段:\n", src)
        except:
            pass
        return False

    print("🔑 填写密码...")
    password_filled = False
    for sel in ['input[type="password"]', 'input[name="password"]', 'input[placeholder*="Password" i]']:
        try:
            if sb.is_element_visible(sel, timeout=3):
                sb.clear(sel)
                sb.type(sel, password, timeout=8)
                password_filled = True
                print(f"   ✅ 密码已填写，选择器: {sel}")
                break
        except:
            continue

    if not password_filled:
        print("❌ 无法找到密码输入框")
        sb.save_screenshot("login_failed.png")
        return False

    time.sleep(1)

    # 再次检查 Cloudflare（有时填完账号后才弹出）
    handle_cloudflare(sb)
    time.sleep(2)

    print("⏳ 等待验证 token 生效...")
    time.sleep(2)

    # 点击登录（带重试）
    for attempt in range(4):
        print(f"🔑 点击登录按钮...(第 {attempt + 1} 次)")
        clicked = False
        for sel in ['button:contains("Login")', 'button[type="submit"]', 'button:contains("Sign in")', 'button:contains("Log in")']:
            try:
                if sb.is_element_visible(sel, timeout=2):
                    sb.uc_click(sel)
                    clicked = True
                    print(f"   使用选择器点击: {sel}")
                    break
            except:
                continue

        if not clicked:
            # JS 兜底
            try:
                sb.execute_script("""
                    const btns = document.querySelectorAll('button');
                    for (let b of btns) {
                        const t = (b.innerText || b.textContent || '').toLowerCase();
                        if (t.includes('login') || t.includes('sign in') || t.includes('log in')) {
                            b.click(); return true;
                        }
                    }
                    // 最后尝试 submit
                    const submit = document.querySelector('button[type="submit"]');
                    if (submit) { submit.click(); return true; }
                    return false;
                """)
                clicked = True
                print("   通过 JS 点击登录")
            except Exception as e:
                print(f"   JS 点击失败: {e}")

        # 等待跳转
        for _ in range(10):
            current_url = sb.get_current_url()
            if "login" not in current_url.lower():
                print(f"✅ 登录成功！当前页面: {current_url}")
                return True
            time.sleep(1)

        # 检查是否有错误提示
        try:
            for sel in ['.alert-danger', '[role="alert"]', '.text-danger', '.error', '.toast-error']:
                if sb.is_element_visible(sel, timeout=1):
                    print(f"❌ 页面错误提示: {sb.get_text(sel)}")
        except:
            pass

        print("⚠️ 未跳转成功，准备重试...")
        time.sleep(2)

    print(f"❌ 登录失败，当前 URL: {sb.get_current_url()}")
    sb.save_screenshot("login_failed.png")
    return False


def click_renew(sb):
    print("📄 进入服务器面板...")
    sb.open(SERVER_URL)
    sb.wait_for_ready_state_complete()
    time.sleep(4)

    print("🔍 查找 Renew 按钮...")
    renew_selectors = [
        'button:contains("Renew")',
        'button:contains("续期")',
        '//button[contains(translate(text(),"RENEW","renew"),"renew")]',
        'button >> text=/Renew/i',
    ]

    for sel in renew_selectors:
        try:
            if sb.is_element_visible(sel, timeout=5):
                print(f"✅ 找到 Renew 按钮: {sel}")
                sb.uc_click(sel)
                print("✅ 已点击 Renew")
                time.sleep(4)
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
            time.sleep(4)
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

    print("🚀 启动 SkyMC 自动续期脚本 v5 (SeleniumBase UC 模式)")
    print(f"目标服务器: {SERVER_URL}")

    current_ip = get_current_ip()
    print(f"🎯 当前出口 IP: {current_ip}")

    sb_kwargs = {
        "uc": True,
        "headless": False,   # uc_gui_click_captcha 需要 GUI
        "locale_code": "en",
    }
    if IS_PROXY:
        sb_kwargs["proxy"] = PROXY_SERVER
        print(f"⚙️ 已启用代理: {PROXY_SERVER}")

    with SB(**sb_kwargs) as sb:
        success = login(sb, EMAIL, PASSWORD)
        if not success:
            msg = f"❌ 登录失败\nIP: {current_ip}\n请检查账号密码或 Cloudflare 验证情况"
            print(msg)
            send_tg(TG_BOT_TOKEN, TG_CHAT_ID, msg, image_path="login_failed.png")
            return

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

        sb.save_screenshot("final_result.png")
        print("📸 最终截图已保存: final_result.png")

    print("🏁 脚本执行完毕")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SkyMC 免费服务器自动续期脚本 v7
重点强化 Cloudflare Turnstile 处理时机与重试
"""

import os
import sys
import time
import requests
from seleniumbase import SB

# ==================== 配置 ====================
EMAIL = os.environ.get("SKYMC_EMAIL") or os.environ.get("EMAIL") or ""
PASSWORD = os.environ.get("SKYMC_PASSWORD") or os.environ.get("PASSWORD") or ""
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN") or ""
TG_CHAT_ID = os.environ.get("TG_CHAT_ID") or ""

SERVER_URL = os.environ.get("SERVER_URL") or "https://skymc.org/en/server/TuUzR_dWxO2P"
LOGIN_URL = "https://skymc.org/en/login"

IS_PROXY = os.environ.get("IS_PROXY", "false").lower() == "true"
PROXY_SERVER = os.environ.get("PROXY_SERVER") or "socks5://127.0.0.1:1080"
REQUESTS_PROXIES = {"http": PROXY_SERVER, "https": PROXY_SERVER} if IS_PROXY else None
# ==============================================


def send_tg(token, chat_id, message, image_path=None):
    if not token or not chat_id:
        print("⚠️  未配置 TG_BOT_TOKEN 或 TG_CHAT_ID，跳过通知")
        return
    message = f"【SkyMC 续期】\n{message}"
    if image_path and os.path.exists(image_path):
        try:
            with open(image_path, "rb") as f:
                resp = requests.post(
                    f"https://api.telegram.org/bot{token}/sendPhoto",
                    data={"chat_id": chat_id, "caption": message},
                    files={"photo": f},
                    timeout=20,
                    proxies=REQUESTS_PROXIES,
                )
            if resp.status_code == 200:
                print("📨 Telegram 通知已发送（附带图片）")
                return
        except Exception as e:
            print(f"⚠️ 带图发送异常: {e}")
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": message},
            timeout=10,
            proxies=REQUESTS_PROXIES,
        )
        if resp.status_code == 200:
            print("📨 Telegram 通知已发送（纯文字）")
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


def is_cloudflare_present(sb):
    """判断当前是否存在 Cloudflare 验证"""
    try:
        src = sb.get_page_source().lower()
        keywords = [
            "security verification",
            "verify you are human",
            "cf-turnstile",
            "turnstile",
            "challenges.cloudflare.com",
            "cf-challenge",
        ]
        return any(k in src for k in keywords)
    except:
        return False


def handle_cloudflare(sb, max_retry=3):
    """更强力的 Cloudflare 处理"""
    if not is_cloudflare_present(sb):
        return True

    print("🛡  检测到 Cloudflare 验证，开始处理...")

    for i in range(max_retry):
        print(f"   第 {i+1} 次尝试通过验证...")

        # 方法1：官方推荐的 uc_gui_click_captcha
        try:
            sb.uc_gui_click_captcha()
            print("   ✅ uc_gui_click_captcha 已调用")
            time.sleep(5)
            if not is_cloudflare_present(sb):
                print("   ✅ 验证已通过！")
                return True
        except Exception as e:
            print(f"   uc_gui_click_captcha 异常: {e}")

        # 方法2：直接点击 checkbox
        try:
            sb.uc_click('input[type="checkbox"]', timeout=4)
            print("   ✅ 已点击 checkbox")
            time.sleep(4)
            if not is_cloudflare_present(sb):
                print("   ✅ 验证已通过！")
                return True
        except:
            pass

        # 方法3：JS 点击可能的验证元素
        try:
            sb.execute_script("""
                // 尝试点击 Turnstile 相关元素
                const selectors = [
                    'input[type="checkbox"]',
                    '.cf-turnstile',
                    '#cf-turnstile',
                    'label',
                    '[data-sitekey]',
                    'iframe'
                ];
                for (const sel of selectors) {
                    const el = document.querySelector(sel);
                    if (el) {
                        el.click();
                    }
                }
                // 尝试点击 iframe 内
                const iframes = document.querySelectorAll('iframe');
                iframes.forEach(iframe => {
                    try {
                        const doc = iframe.contentDocument || iframe.contentWindow.document;
                        const cb = doc.querySelector('input[type="checkbox"]');
                        if (cb) cb.click();
                    } catch(e) {}
                });
            """)
            print("   ✅ JS 点击已执行")
            time.sleep(4)
            if not is_cloudflare_present(sb):
                print("   ✅ 验证已通过！")
                return True
        except Exception as e:
            print(f"   JS 点击异常: {e}")

        time.sleep(2)

    print("   ❌ Cloudflare 验证未能自动通过")
    return False


def fill_input_js(sb, value, is_password=False):
    js_code = f"""
    const inputs = document.querySelectorAll('input');
    for (let input of inputs) {{
        const type = (input.type || '').toLowerCase();
        const placeholder = (input.placeholder || '').toLowerCase();
        const name = (input.name || '').toLowerCase();
        const id = (input.id || '').toLowerCase();
        const isPwd = type === 'password' || name.includes('pass') || id.includes('pass') || placeholder.includes('password');
        
        if ({str(is_password).lower()}) {{
            if (isPwd && input.offsetParent !== null) {{
                input.focus();
                input.value = '';
                input.value = `{value}`;
                input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                return true;
            }}
        }} else {{
            if (!isPwd && type !== 'hidden' && type !== 'submit' && type !== 'checkbox' && type !== 'radio' && input.offsetParent !== null) {{
                input.focus();
                input.value = '';
                input.value = `{value}`;
                input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                return true;
            }}
        }}
    }}
    return false;
    """
    try:
        return sb.execute_script(js_code)
    except:
        return False


def login(sb, email, password):
    print("🌐 打开登录页面...")
    sb.open(LOGIN_URL)
    sb.wait_for_ready_state_complete()
    time.sleep(3)

    # 1. 打开页面后先处理可能的验证
    handle_cloudflare(sb)
    time.sleep(1)

    # 2. 填写邮箱
    print("📧 填写邮箱/用户名...")
    email_filled = False
    for sel in [
        'input[placeholder*="Username or Email" i]',
        'input[placeholder*="Email" i]',
        'input[type="email"]',
        'input[type="text"]',
    ]:
        try:
            if sb.is_element_visible(sel, timeout=2):
                sb.clear(sel)
                sb.type(sel, email, timeout=6)
                email_filled = True
                print(f"   ✅ 邮箱已填写（{sel}）")
                break
        except:
            continue
    if not email_filled:
        if fill_input_js(sb, email, is_password=False):
            email_filled = True
            print("   ✅ 通过 JS 填写邮箱成功")
    if not email_filled:
        print("❌ 无法找到邮箱输入框")
        sb.save_screenshot("login_failed.png")
        return False

    time.sleep(0.8)

    # 3. 填写密码
    print("🔑 填写密码...")
    password_filled = False
    for sel in ['input[type="password"]', 'input[name="password"]']:
        try:
            if sb.is_element_visible(sel, timeout=2):
                sb.clear(sel)
                sb.type(sel, password, timeout=6)
                password_filled = True
                print(f"   ✅ 密码已填写（{sel}）")
                break
        except:
            continue
    if not password_filled:
        if fill_input_js(sb, password, is_password=True):
            password_filled = True
            print("   ✅ 通过 JS 填写密码成功")
    if not password_filled:
        print("❌ 无法找到密码输入框")
        sb.save_screenshot("login_failed.png")
        return False

    time.sleep(1)

    # 4. 填完后再处理一次验证（有时验证在填完后才出现）
    handle_cloudflare(sb)
    time.sleep(2)

    print("⏳ 等待验证 token 生效...")
    time.sleep(3)

    # 5. 点击登录 + 登录后再次处理验证
    for attempt in range(5):
        print(f"🔑 点击登录按钮...(第 {attempt + 1} 次)")

        # 点击登录
        try:
            sb.uc_click('button:contains("Login")')
        except:
            try:
                sb.execute_script("""
                    const btns = document.querySelectorAll('button');
                    for (let b of btns) {
                        const t = (b.innerText || '').toLowerCase();
                        if (t.includes('login') || t.includes('sign in')) {
                            b.click(); return;
                        }
                    }
                    const s = document.querySelector('button[type="submit"]');
                    if (s) s.click();
                """)
            except:
                pass

        time.sleep(3)

        # 关键：点击登录后立刻检查并处理 Cloudflare
        if is_cloudflare_present(sb):
            print("   点击登录后出现验证，正在处理...")
            handle_cloudflare(sb, max_retry=4)
            time.sleep(3)

        # 检查是否已跳转
        for _ in range(8):
            current_url = sb.get_current_url()
            if "login" not in current_url.lower():
                print(f"✅ 登录成功！当前页面: {current_url}")
                return True
            # 中途如果又出现验证，再处理一次
            if is_cloudflare_present(sb):
                handle_cloudflare(sb, max_retry=2)
            time.sleep(1)

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

    # 面板也可能触发验证
    handle_cloudflare(sb)

    print("🔍 查找 Renew 按钮...")
    for sel in ['button:contains("Renew")', 'button:contains("续期")']:
        try:
            if sb.is_element_visible(sel, timeout=5):
                print(f"✅ 找到 Renew 按钮: {sel}")
                sb.uc_click(sel)
                print("✅ 已点击 Renew")
                time.sleep(4)
                return True
        except:
            continue

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

    print("🚀 启动 SkyMC 自动续期脚本 v7")
    print(f"目标服务器: {SERVER_URL}")

    current_ip = get_current_ip()
    print(f"🎯 当前出口 IP: {current_ip}")

    sb_kwargs = {
        "uc": True,
        "headless": False,
        "locale_code": "en",
    }
    if IS_PROXY:
        sb_kwargs["proxy"] = PROXY_SERVER
        print(f"⚙️ 已启用代理: {PROXY_SERVER}")

    with SB(**sb_kwargs) as sb:
        success = login(sb, EMAIL, PASSWORD)
        if not success:
            msg = f"❌ 登录失败（大概率是 Cloudflare 验证未通过）\nIP: {current_ip}"
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
            msg = f"❌ 续期失败，未找到 Renew 按钮\nIP: {current_ip}"
            send_tg(TG_BOT_TOKEN, TG_CHAT_ID, msg, image_path="renew_not_found.png")
            print(msg)

        sb.save_screenshot("final_result.png")
        print("📸 最终截图已保存")

    print("🏁 脚本执行完毕")


if __name__ == "__main__":
    main()

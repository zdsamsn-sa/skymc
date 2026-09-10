#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SkyMC 免费服务器自动续期脚本 v8
修复 JS SyntaxError + 加强面板页 Cloudflare 处理 + 续期后确认
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
    try:
        src = sb.get_page_source().lower()
        keywords = [
            "security verification",
            "verify you are human",
            "cf-turnstile",
            "turnstile",
            "challenges.cloudflare.com",
        ]
        return any(k in src for k in keywords)
    except:
        return False


def handle_cloudflare(sb, max_retry=3):
    if not is_cloudflare_present(sb):
        return True

    print("🛡  检测到 Cloudflare 验证，开始处理...")

    for i in range(max_retry):
        print(f"   第 {i+1} 次尝试通过验证...")

        # 方法1：uc_gui_click_captcha
        try:
            sb.uc_gui_click_captcha()
            print("   ✅ uc_gui_click_captcha 已调用")
            time.sleep(5)
            if not is_cloudflare_present(sb):
                print("   ✅ 验证已通过！")
                return True
        except Exception as e:
            print(f"   uc_gui_click_captcha 异常: {e}")

        # 方法2：点击 checkbox
        try:
            sb.uc_click('input[type="checkbox"]', timeout=4)
            print("   ✅ 已点击 checkbox")
            time.sleep(4)
            if not is_cloudflare_present(sb):
                print("   ✅ 验证已通过！")
                return True
        except:
            pass

        # 方法3：修复后的 JS（不再重复声明 selectors）
        try:
            sb.execute_script("""
                (function() {
                    var sels = [
                        'input[type="checkbox"]',
                        '.cf-turnstile',
                        '#cf-turnstile',
                        'label',
                        '[data-sitekey]'
                    ];
                    for (var i = 0; i < sels.length; i++) {
                        var el = document.querySelector(sels[i]);
                        if (el) {
                            try { el.click(); } catch(e) {}
                        }
                    }
                    var iframes = document.querySelectorAll('iframe');
                    for (var j = 0; j < iframes.length; j++) {
                        try {
                            var doc = iframes[j].contentDocument || iframes[j].contentWindow.document;
                            var cb = doc.querySelector('input[type="checkbox"]');
                            if (cb) cb.click();
                        } catch(e) {}
                    }
                })();
            """)
            print("   ✅ JS 点击已执行")
            time.sleep(4)
            if not is_cloudflare_present(sb):
                print("   ✅ 验证已通过！")
                return True
        except Exception as e:
            print(f"   JS 点击异常: {e}")

        time.sleep(2)

    print("   ⚠️ Cloudflare 验证未能完全通过，继续尝试后续流程...")
    return False


def fill_input_js(sb, value, is_password=False):
    js_code = f"""
    (function() {{
        var inputs = document.querySelectorAll('input');
        for (var i = 0; i < inputs.length; i++) {{
            var input = inputs[i];
            var type = (input.type || '').toLowerCase();
            var placeholder = (input.placeholder || '').toLowerCase();
            var name = (input.name || '').toLowerCase();
            var id = (input.id || '').toLowerCase();
            var isPwd = type === 'password' || name.indexOf('pass') >= 0 || id.indexOf('pass') >= 0 || placeholder.indexOf('password') >= 0;
            
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
    }})();
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

    handle_cloudflare(sb)
    time.sleep(1)

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
                print(f"   ✅ 邮箱已填写")
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

    print("🔑 填写密码...")
    password_filled = False
    for sel in ['input[type="password"]', 'input[name="password"]']:
        try:
            if sb.is_element_visible(sel, timeout=2):
                sb.clear(sel)
                sb.type(sel, password, timeout=6)
                password_filled = True
                print(f"   ✅ 密码已填写")
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
    handle_cloudflare(sb)
    time.sleep(2)

    print("⏳ 等待验证 token 生效...")
    time.sleep(3)

    for attempt in range(5):
        print(f"🔑 点击登录按钮...(第 {attempt + 1} 次)")

        try:
            sb.uc_click('button:contains("Login")')
        except:
            try:
                sb.execute_script("""
                    (function() {
                        var btns = document.querySelectorAll('button');
                        for (var i = 0; i < btns.length; i++) {
                            var t = (btns[i].innerText || '').toLowerCase();
                            if (t.indexOf('login') >= 0 || t.indexOf('sign in') >= 0) {
                                btns[i].click();
                                return;
                            }
                        }
                        var s = document.querySelector('button[type="submit"]');
                        if (s) s.click();
                    })();
                """)
            except:
                pass

        time.sleep(3)

        if is_cloudflare_present(sb):
            print("   点击登录后出现验证，正在处理...")
            handle_cloudflare(sb, max_retry=4)
            time.sleep(3)

        for _ in range(8):
            current_url = sb.get_current_url()
            if "login" not in current_url.lower():
                print(f"✅ 登录成功！当前页面: {current_url}")
                return True
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

    # 面板页也可能弹验证
    handle_cloudflare(sb)
    time.sleep(2)

    print("🔍 查找 Renew 按钮...")
    clicked = False

    for sel in ['button:contains("Renew")', 'button:contains("续期")']:
        try:
            if sb.is_element_visible(sel, timeout=5):
                print(f"✅ 找到 Renew 按钮: {sel}")
                sb.uc_click(sel)
                clicked = True
                print("✅ 已点击 Renew")
                break
        except:
            continue

    if not clicked:
        try:
            result = sb.execute_script("""
                (function() {
                    var buttons = document.querySelectorAll('button');
                    for (var i = 0; i < buttons.length; i++) {
                        var text = (buttons[i].innerText || buttons[i].textContent || '').toLowerCase();
                        if (text.indexOf('renew') >= 0 || text.indexOf('续期') >= 0) {
                            buttons[i].click();
                            return true;
                        }
                    }
                    return false;
                })();
            """)
            if result:
                print("✅ 通过 JavaScript 点击 Renew 成功")
                clicked = True
        except Exception as e:
            print(f"⚠️ JS 点击失败: {e}")

    if not clicked:
        print("❌ 未找到 Renew 按钮")
        sb.save_screenshot("renew_not_found.png")
        return False

    time.sleep(3)

    # 点击 Renew 后可能再次弹出 Cloudflare，再处理一次
    if is_cloudflare_present(sb):
        print("   点击 Renew 后出现验证，正在处理...")
        handle_cloudflare(sb, max_retry=3)
        time.sleep(3)

    # 再点一次 Renew（防止被验证打断）
    try:
        sb.execute_script("""
            (function() {
                var buttons = document.querySelectorAll('button');
                for (var i = 0; i < buttons.length; i++) {
                    var text = (buttons[i].innerText || buttons[i].textContent || '').toLowerCase();
                    if (text.indexOf('renew') >= 0 || text.indexOf('续期') >= 0) {
                        buttons[i].click();
                        return true;
                    }
                }
                return false;
            })();
        """)
        print("   已再次尝试点击 Renew")
        time.sleep(3)
    except:
        pass

    return True


def main():
    if not EMAIL or not PASSWORD:
        print("❌ 请设置环境变量 SKYMC_EMAIL 和 SKYMC_PASSWORD")
        sys.exit(1)

    print("🚀 启动 SkyMC 自动续期脚本 v8")
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

        time.sleep(2)
        sb.save_screenshot("final_result.png")

        if renew_ok:
            msg = f"✅ 续期流程已执行（已尝试点击 Renew）\n服务器: TuUzR_dWxO2P\nIP: {current_ip}\n请查看截图确认倒计时是否已重置"
            send_tg(TG_BOT_TOKEN, TG_CHAT_ID, msg, image_path="final_result.png")
            print(msg)
        else:
            msg = f"❌ 续期失败，未找到 Renew 按钮\nIP: {current_ip}"
            send_tg(TG_BOT_TOKEN, TG_CHAT_ID, msg, image_path="renew_not_found.png")
            print(msg)

        print("📸 最终截图已保存")

    print("🏁 脚本执行完毕")


if __name__ == "__main__":
    main()

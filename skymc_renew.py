#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SkyMC 免费服务器自动续期脚本 v6
修复：密码输入框选择器 + JS 兜底填写
目标：https://skymc.org/ → 登录 → 进入服务器面板 → 点击 Renew
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
BASE_URL = "https://skymc.org/"

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
            try:
                sb.uc_click('input[type="checkbox"]', timeout=5)
                print("✅ 备用 checkbox 点击完成")
                time.sleep(3)
                return True
            except:
                pass
            return False
    return True


def fill_input_js(sb, value, is_password=False):
    """用 JS 强制填写输入框（最强兜底）"""
    js_code = f"""
    const inputs = document.querySelectorAll('input');
    for (let input of inputs) {{
        const type = (input.type || '').toLowerCase();
        const placeholder = (input.placeholder || '').toLowerCase();
        const name = (input.name || '').toLowerCase();
        const id = (input.id || '').toLowerCase();
        
        const isPwd = type === 'password' || name.includes('pass') || id.includes('pass') || placeholder.includes('password');
        
        if ({str(is_password).lower()}) {{
            // 找密码框
            if (isPwd && input.offsetParent !== null) {{
                input.focus();
                input.value = '';
                input.value = `{value}`;
                input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                input.dispatchEvent(new Event('blur', {{ bubbles: true }}));
                return 'password';
            }}
        }} else {{
            // 找邮箱/用户名框
            if (!isPwd && type !== 'hidden' && type !== 'submit' && type !== 'checkbox' && type !== 'radio' && input.offsetParent !== null) {{
                input.focus();
                input.value = '';
                input.value = `{value}`;
                input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                input.dispatchEvent(new Event('blur', {{ bubbles: true }}));
                return 'email';
            }}
        }}
    }}
    return null;
    """
    try:
        result = sb.execute_script(js_code)
        return result is not None
    except Exception as e:
        print(f"   JS 填写异常: {e}")
        return False


def login(sb, email, password):
    print("🌐 打开登录页面...")
    sb.open(LOGIN_URL)
    sb.wait_for_ready_state_complete()
    time.sleep(3)

    handle_cloudflare(sb)
    time.sleep(1)

    # ========== 填写邮箱 ==========
    print("📧 填写邮箱/用户名...")
    email_filled = False

    # 方法1：常规选择器
    email_selectors = [
        'input[placeholder*="Username or Email" i]',
        'input[placeholder*="Email" i]',
        'input[placeholder*="Username" i]',
        'input[type="email"]',
        'input[name="email"]',
        'input[name="username"]',
        'input[type="text"]',
    ]
    for sel in email_selectors:
        try:
            if sb.is_element_visible(sel, timeout=2):
                sb.clear(sel)
                sb.type(sel, email, timeout=6)
                email_filled = True
                print(f"   ✅ 邮箱已填写（选择器: {sel}）")
                break
        except:
            continue

    # 方法2：JS 兜底
    if not email_filled:
        print("   尝试 JS 方式填写邮箱...")
        if fill_input_js(sb, email, is_password=False):
            email_filled = True
            print("   ✅ 通过 JS 填写邮箱成功")

    if not email_filled:
        print("❌ 无法找到邮箱输入框")
        sb.save_screenshot("login_failed.png")
        return False

    time.sleep(0.8)

    # ========== 填写密码 ==========
    print("🔑 填写密码...")
    password_filled = False

    # 方法1：常规选择器
    password_selectors = [
        'input[type="password"]',
        'input[name="password"]',
        'input[placeholder*="Password" i]',
        'input[placeholder*="密码"]',
        'input[id*="password" i]',
        'input[id*="pass" i]',
    ]
    for sel in password_selectors:
        try:
            if sb.is_element_visible(sel, timeout=2):
                sb.clear(sel)
                sb.type(sel, password, timeout=6)
                password_filled = True
                print(f"   ✅ 密码已填写（选择器: {sel}）")
                break
        except Exception as e:
            continue

    # 方法2：JS 兜底（重点加强）
    if not password_filled:
        print("   尝试 JS 方式填写密码...")
        if fill_input_js(sb, password, is_password=True):
            password_filled = True
            print("   ✅ 通过 JS 填写密码成功")

    # 方法3：再试一次 Selenium 原生
    if not password_filled:
        try:
            print("   最后尝试 Selenium 原生 password 定位...")
            elements = sb.find_elements('input[type="password"]')
            if elements:
                elements[0].clear()
                elements[0].send_keys(password)
                password_filled = True
                print("   ✅ 原生方式填写密码成功")
        except Exception as e:
            print(f"   原生方式失败: {e}")

    if not password_filled:
        print("❌ 无法找到密码输入框")
        sb.save_screenshot("login_failed.png")
        try:
            # 打印所有 input 信息帮助调试
            info = sb.execute_script("""
                const inputs = document.querySelectorAll('input');
                let result = [];
                inputs.forEach((inp, i) => {
                    result.push({
                        index: i,
                        type: inp.type,
                        name: inp.name,
                        id: inp.id,
                        placeholder: inp.placeholder,
                        visible: inp.offsetParent !== null
                    });
                });
                return JSON.stringify(result, null, 2);
            """)
            print("页面所有 input 元素信息:\n", info)
        except:
            pass
        return False

    time.sleep(1)

    # 再次处理可能出现的验证
    handle_cloudflare(sb)
    time.sleep(2)

    print("⏳ 等待验证 token 生效...")
    time.sleep(2)

    # ========== 点击登录 ==========
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
            try:
                sb.execute_script("""
                    const btns = document.querySelectorAll('button');
                    for (let b of btns) {
                        const t = (b.innerText || b.textContent || '').toLowerCase();
                        if (t.includes('login') || t.includes('sign in') || t.includes('log in')) {
                            b.click(); return true;
                        }
                    }
                    const submit = document.querySelector('button[type="submit"]');
                    if (submit) { submit.click(); return true; }
                    return false;
                """)
                clicked = True
                print("   通过 JS 点击登录")
            except Exception as e:
                print(f"   JS 点击失败: {e}")

        # 等待跳转
        for _ in range(12):
            current_url = sb.get_current_url()
            if "login" not in current_url.lower():
                print(f"✅ 登录成功！当前页面: {current_url}")
                return True
            time.sleep(1)

        try:
            for sel in ['.alert-danger', '[role="alert"]', '.text-danger', '.error']:
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

    print("🚀 启动 SkyMC 自动续期脚本 v6")
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

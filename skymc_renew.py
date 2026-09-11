#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SkyMC 自动续期脚本 v10

根据实际页面 HTML 修复输入框选择器：
  邮箱: input#usernameOrEmail-s1  name=identifier  type=text
  密码: input#password-s1         name=password    type=password
"""

import os
import sys
import time
import json
import requests
from seleniumbase import SB

EMAIL = os.environ.get("SKYMC_EMAIL") or os.environ.get("EMAIL") or ""
PASSWORD = os.environ.get("SKYMC_PASSWORD") or os.environ.get("PASSWORD") or ""
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN") or ""
TG_CHAT_ID = os.environ.get("TG_CHAT_ID") or ""

SERVER_URL = os.environ.get("SERVER_URL") or "https://skymc.org/en/server/TuUzR_dWxO2P"
LOGIN_URL = "https://skymc.org/en/login"

IS_PROXY = os.environ.get("IS_PROXY", "false").lower() == "true"
PROXY_SERVER = os.environ.get("PROXY_SERVER") or "socks5://127.0.0.1:1080"
REQUESTS_PROXIES = {"http": PROXY_SERVER, "https": PROXY_SERVER} if IS_PROXY else None

# 从失败日志确认的真实选择器
EMAIL_SELECTORS = [
    "#usernameOrEmail-s1",
    'input[name="identifier"]',
    'input[id*="usernameOrEmail"]',
    'input[id*="username"]',
]
PASSWORD_SELECTORS = [
    "#password-s1",
    'input[name="password"]',
    'input[type="password"]',
    'input[id*="password"]',
]


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
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": message},
            timeout=10,
            proxies=REQUESTS_PROXIES,
        )
        print("📨 Telegram 通知已发送（纯文字）")
    except Exception as e:
        print(f"❌ Telegram 发送异常: {e}")


def get_current_ip():
    try:
        resp = requests.get("https://api.ip.sb/ip", proxies=REQUESTS_PROXIES, timeout=10)
        if resp.status_code == 200:
            return resp.text.strip()
    except Exception:
        pass
    return "获取失败"


def dump_inputs(sb):
    try:
        info = sb.execute_script(
            """
            var inputs = document.querySelectorAll('input');
            var result = [];
            for (var i = 0; i < inputs.length; i++) {
                var inp = inputs[i];
                result.push({
                    type: inp.type,
                    name: inp.name,
                    id: inp.id,
                    placeholder: inp.placeholder,
                    visible: inp.offsetParent !== null,
                    valueLen: (inp.value || '').length
                });
            }
            return JSON.stringify(result);
            """
        )
        print("页面 input 信息:", info)
        return info
    except Exception as e:
        print("dump_inputs 失败:", e)
        return None


def challenge_visible(sb):
    """只在真正弹出人机验证时才处理，避免页面源码里有 turnstile 脚本就误判"""
    try:
        src = sb.get_page_source()
        return ("Verify you are human" in src) or ("Security Verification" in src)
    except Exception:
        return False


def handle_cloudflare(sb, max_retry=3):
    if not challenge_visible(sb):
        return True
    print("🛡  检测到 Cloudflare 人机验证弹窗，开始处理...")
    for i in range(max_retry):
        print(f"   第 {i + 1} 次尝试...")
        try:
            sb.uc_gui_click_captcha()
            print("   ✅ uc_gui_click_captcha 已调用")
            time.sleep(5)
            if not challenge_visible(sb):
                print("   ✅ 验证已通过")
                return True
        except Exception as e:
            print(f"   uc_gui_click_captcha 异常: {e}")
        time.sleep(2)
    print("   ⚠️ 验证未完全通过，继续后续流程")
    return False


def js_set_value(sb, selectors, value):
    """用 arguments 传值，避免字符串转义问题"""
    script = """
        var selectors = arguments[0];
        var value = arguments[1];
        for (var s = 0; s < selectors.length; s++) {
            var el = null;
            try { el = document.querySelector(selectors[s]); } catch (e) {}
            if (!el) continue;
            el.focus();
            el.value = '';
            el.value = value;
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
            el.dispatchEvent(new Event('blur', { bubbles: true }));
            if (el.value === value) return selectors[s];
        }
        return null;
    """
    try:
        return sb.execute_script(script, selectors, value)
    except Exception as e:
        print(f"   JS 填写异常: {e}")
        return None


def fill_field(sb, selectors, value, field_name, timeout=20):
    print(f"   填写 {field_name} ...")
    end = time.time() + timeout
    last_err = None
    while time.time() < end:
        # 1) SeleniumBase type（官方推荐）
        for sel in selectors:
            try:
                sb.wait_for_element_visible(sel, timeout=2)
                sb.clear(sel)
                sb.type(sel, value)
                print(f"   ✅ {field_name} 已填写（{sel}）")
                return True
            except Exception as e:
                last_err = e
                continue

        # 2) JS 按选择器强制赋值
        hit = js_set_value(sb, selectors, value)
        if hit:
            print(f"   ✅ {field_name} 通过 JS 填写成功（{hit}）")
            return True

        time.sleep(1)

    print(f"   ❌ 无法填写 {field_name}，最后错误: {last_err}")
    return False


def click_login(sb):
    selectors = [
        'button:contains("Login")',
        'button[type="submit"]',
        'button:contains("Sign in")',
    ]
    for sel in selectors:
        try:
            if sb.is_element_visible(sel):
                sb.uc_click(sel)
                print(f"   已点击登录（{sel}）")
                return True
        except Exception:
            continue
    try:
        sb.execute_script(
            """
            var btns = document.querySelectorAll('button');
            for (var i = 0; i < btns.length; i++) {
                var t = (btns[i].innerText || '').toLowerCase();
                if (t.indexOf('login') >= 0 || t.indexOf('sign in') >= 0) {
                    btns[i].click();
                    return true;
                }
            }
            var s = document.querySelector('button[type="submit"]');
            if (s) { s.click(); return true; }
            return false;
            """
        )
        print("   已通过 JS 点击登录")
        return True
    except Exception as e:
        print(f"   点击登录失败: {e}")
        return False


def login(sb, email, password):
    print("🌐 打开登录页面...")
    try:
        sb.uc_open_with_reconnect(LOGIN_URL, reconnect_time=6)
    except Exception:
        sb.open(LOGIN_URL)
    sb.wait_for_ready_state_complete()
    time.sleep(3)

    handle_cloudflare(sb)
    time.sleep(1)

    print("📧 填写邮箱/用户名...")
    if not fill_field(sb, EMAIL_SELECTORS, email, "邮箱", timeout=25):
        dump_inputs(sb)
        sb.save_screenshot("login_failed.png")
        return False

    time.sleep(0.5)

    print("🔑 填写密码...")
    if not fill_field(sb, PASSWORD_SELECTORS, password, "密码", timeout=15):
        dump_inputs(sb)
        sb.save_screenshot("login_failed.png")
        return False

    time.sleep(1)
    handle_cloudflare(sb)
    time.sleep(2)

    print("⏳ 等待验证 token 生效...")
    time.sleep(2)

    for attempt in range(5):
        print(f"🔑 点击登录按钮...(第 {attempt + 1} 次)")
        click_login(sb)
        time.sleep(3)

        if challenge_visible(sb):
            print("   点击登录后出现验证，正在处理...")
            handle_cloudflare(sb, max_retry=4)
            time.sleep(3)

        for _ in range(10):
            url = (sb.get_current_url() or "").lower()
            if "login" not in url:
                print(f"✅ 登录成功！当前页面: {sb.get_current_url()}")
                return True
            if challenge_visible(sb):
                handle_cloudflare(sb, max_retry=2)
            time.sleep(1)

        print("⚠️ 未跳转成功，准备重试...")
        time.sleep(2)

    print(f"❌ 登录失败，当前 URL: {sb.get_current_url()}")
    dump_inputs(sb)
    sb.save_screenshot("login_failed.png")
    return False


def click_renew(sb):
    print("📄 进入服务器面板...")
    try:
        sb.uc_open_with_reconnect(SERVER_URL, reconnect_time=5)
    except Exception:
        sb.open(SERVER_URL)
    sb.wait_for_ready_state_complete()
    time.sleep(4)

    handle_cloudflare(sb)
    time.sleep(2)

    print("🔍 查找 Renew 按钮...")
    clicked = False
    for sel in ['button:contains("Renew")', 'button:contains("续期")']:
        try:
            sb.wait_for_element_visible(sel, timeout=6)
            sb.uc_click(sel)
            print(f"✅ 已点击 Renew（{sel}）")
            clicked = True
            break
        except Exception:
            continue

    if not clicked:
        try:
            result = sb.execute_script(
                """
                var buttons = document.querySelectorAll('button');
                for (var i = 0; i < buttons.length; i++) {
                    var text = (buttons[i].innerText || buttons[i].textContent || '').toLowerCase();
                    if (text.indexOf('renew') >= 0 || text.indexOf('续期') >= 0) {
                        buttons[i].click();
                        return true;
                    }
                }
                return false;
                """
            )
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
    if challenge_visible(sb):
        print("   点击 Renew 后出现验证，正在处理...")
        handle_cloudflare(sb, max_retry=3)
        time.sleep(3)
        try:
            sb.execute_script(
                """
                var buttons = document.querySelectorAll('button');
                for (var i = 0; i < buttons.length; i++) {
                    var text = (buttons[i].innerText || '').toLowerCase();
                    if (text.indexOf('renew') >= 0 || text.indexOf('续期') >= 0) {
                        buttons[i].click();
                        return true;
                    }
                }
                return false;
                """
            )
            print("   已再次尝试点击 Renew")
        except Exception:
            pass
    return True


def main():
    if not EMAIL or not PASSWORD:
        print("❌ 请设置环境变量 SKYMC_EMAIL 和 SKYMC_PASSWORD")
        sys.exit(1)

    print("🚀 启动 SkyMC 自动续期脚本 v10")
    print(f"目标服务器: {SERVER_URL}")
    current_ip = get_current_ip()
    print(f"🎯 当前出口 IP: {current_ip}")

    sb_kwargs = {"uc": True, "headless": False, "locale_code": "en"}
    if IS_PROXY:
        sb_kwargs["proxy"] = PROXY_SERVER
        print(f"⚙️ 已启用代理: {PROXY_SERVER}")

    with SB(**sb_kwargs) as sb:
        if not login(sb, EMAIL, PASSWORD):
            msg = f"❌ 登录失败\nIP: {current_ip}"
            print(msg)
            send_tg(TG_BOT_TOKEN, TG_CHAT_ID, msg, image_path="login_failed.png")
            return

        print("\n📄 开始续期流程...")
        renew_ok = click_renew(sb)
        time.sleep(2)
        sb.save_screenshot("final_result.png")

        if renew_ok:
            msg = (
                f"✅ 续期流程已执行\n服务器: TuUzR_dWxO2P\n"
                f"IP: {current_ip}\n请查看截图确认倒计时是否已重置"
            )
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

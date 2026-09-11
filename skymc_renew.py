#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SkyMC 自动续期脚本 v11

v10 已能登录 + 点击 Renew。
v11 新增：
  1. 读取面板状态 / 剩余时间
  2. 关机则点击 Start
  3. 续期后再次读取剩余时间并对比
  4. 等 Cloudflare 弹窗消失后再截图，保证截图内容正确
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
SERVER_ID = "TuUzR_dWxO2P"

IS_PROXY = os.environ.get("IS_PROXY", "false").lower() == "true"
PROXY_SERVER = os.environ.get("PROXY_SERVER") or "socks5://127.0.0.1:1080"
REQUESTS_PROXIES = {"http": PROXY_SERVER, "https": PROXY_SERVER} if IS_PROXY else None

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
                    data={"chat_id": chat_id, "caption": message[:1024]},
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
                    type: inp.type, name: inp.name, id: inp.id,
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


def wait_challenge_gone(sb, timeout=20):
    """等验证弹窗消失，避免截图被挡住"""
    end = time.time() + timeout
    while time.time() < end:
        if not challenge_visible(sb):
            return True
        handle_cloudflare(sb, max_retry=1)
        time.sleep(1)
    return not challenge_visible(sb)


def safe_screenshot(sb, path):
    wait_challenge_gone(sb, timeout=12)
    time.sleep(1)
    sb.save_screenshot(path)
    print(f"📸 已保存截图: {path}")
    return path


def js_set_value(sb, selectors, value):
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
                    btns[i].click(); return true;
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
        safe_screenshot(sb, "login_failed.png")
        return False

    time.sleep(0.5)

    print("🔑 填写密码...")
    if not fill_field(sb, PASSWORD_SELECTORS, password, "密码", timeout=15):
        dump_inputs(sb)
        safe_screenshot(sb, "login_failed.png")
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
    safe_screenshot(sb, "login_failed.png")
    return False


def open_server_panel(sb):
    print("📄 进入服务器面板...")
    try:
        sb.uc_open_with_reconnect(SERVER_URL, reconnect_time=5)
    except Exception:
        sb.open(SERVER_URL)
    sb.wait_for_ready_state_complete()
    time.sleep(4)
    handle_cloudflare(sb)
    wait_challenge_gone(sb, timeout=15)
    time.sleep(2)


def read_panel_info(sb):
    """读取状态、剩余时间、可用按钮"""
    script = r"""
        var body = (document.body && document.body.innerText) ? document.body.innerText : '';
        var status = 'unknown';
        if (/\bOnline\b/i.test(body) || /在线/.test(body)) status = 'Online';
        else if (/\bStarting\b/i.test(body) || /启动中/.test(body)) status = 'Starting';
        else if (/\bStopping\b/i.test(body) || /关闭中/.test(body)) status = 'Stopping';
        else if (/\bOffline\b/i.test(body) || /\bStopped\b/i.test(body) || /离线/.test(body) || /已停止/.test(body)) status = 'Offline';

        var remaining = null;
        var matches = body.match(/\b(\d{1,3}:\d{2})\b/g) || [];
        for (var i = 0; i < matches.length; i++) {
            remaining = matches[i];
            break;
        }

        var hasStart = false, hasStop = false, hasRestart = false, hasRenew = false;
        var buttons = [];
        var btns = document.querySelectorAll('button');
        for (var i = 0; i < btns.length; i++) {
            var b = btns[i];
            var text = (b.innerText || b.textContent || '').replace(/\s+/g, ' ').trim();
            var aria = (b.getAttribute('aria-label') || '') + ' ' + (b.getAttribute('title') || '');
            var html = (b.innerHTML || '').toLowerCase();
            var blob = (text + ' ' + aria).toLowerCase();
            var visible = b.offsetParent !== null;
            var enabled = !b.disabled && visible;
            buttons.push({text: text, disabled: !!b.disabled, visible: visible});
            if (!enabled) continue;
            if (blob.indexOf('start') >= 0 || blob.indexOf('启动') >= 0 || html.indexOf('fa-play') >= 0) hasStart = true;
            if (blob.indexOf('stop') >= 0 || blob.indexOf('停止') >= 0 || blob.indexOf('关机') >= 0) hasStop = true;
            if (blob.indexOf('restart') >= 0 || blob.indexOf('重启') >= 0) hasRestart = true;
            if (blob.indexOf('renew') >= 0 || blob.indexOf('续期') >= 0) hasRenew = true;
        }
        return JSON.stringify({
            status: status,
            remaining: remaining,
            hasStart: hasStart,
            hasStop: hasStop,
            hasRestart: hasRestart,
            hasRenew: hasRenew,
            buttons: buttons
        });
    """
    try:
        raw = sb.execute_script(script)
        info = json.loads(raw) if raw else {}
    except Exception as e:
        print(f"   读取面板信息失败: {e}")
        info = {}
    status = info.get("status") or "unknown"
    remaining = info.get("remaining")
    print(f"   面板状态: {status}  剩余时间: {remaining or '未读到'}  "
          f"Start={info.get('hasStart')} Stop={info.get('hasStop')} Renew={info.get('hasRenew')}")
    return info


def format_remaining(hhmm):
    if not hhmm:
        return "未读到"
    parts = str(hhmm).split(":")
    try:
        if len(parts) == 2:
            h, m = int(parts[0]), int(parts[1])
            return f"{hhmm}（{h}小时{m}分钟）"
        if len(parts) == 3:
            h, m, s = int(parts[0]), int(parts[1]), int(parts[2])
            return f"{hhmm}（{h}小时{m}分{s}秒）"
    except Exception:
        pass
    return str(hhmm)


def remaining_to_minutes(hhmm):
    if not hhmm:
        return None
    parts = str(hhmm).split(":")
    try:
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        if len(parts) == 3:
            return int(parts[0]) * 60 + int(parts[1])
    except Exception:
        return None
    return None


def click_named_button(sb, names):
    names_l = [n.lower() for n in names]
    for name in names:
        sel = f'button:contains("{name}")'
        try:
            if sb.is_element_visible(sel) and sb.is_element_enabled(sel):
                sb.uc_click(sel)
                print(f"   已点击按钮: {name}")
                return True
        except Exception:
            continue
    try:
        result = sb.execute_script(
            """
            var names = arguments[0];
            var buttons = document.querySelectorAll('button');
            for (var i = 0; i < buttons.length; i++) {
                var b = buttons[i];
                if (b.disabled || b.offsetParent === null) continue;
                var blob = ((b.innerText || '') + ' ' + (b.getAttribute('aria-label') || '') + ' ' + (b.innerHTML || '')).toLowerCase();
                for (var j = 0; j < names.length; j++) {
                    if (blob.indexOf(names[j]) >= 0) {
                        b.click();
                        return names[j];
                    }
                }
            }
            return null;
            """,
            names_l,
        )
        if result:
            print(f"   已通过 JS 点击按钮: {result}")
            return True
    except Exception as e:
        print(f"   JS 点击按钮失败: {e}")
    return False


def ensure_server_running(sb, info):
    status = (info.get("status") or "").lower()
    has_start = info.get("hasStart")
    has_stop = info.get("hasStop")

    offline = status in ("offline", "stopped", "unknown") and not has_stop
    if status == "online" or has_stop:
        print("   服务器已在运行，无需启动")
        return True, "已在运行"

    if not (offline or has_start or status in ("offline", "stopped", "starting")):
        print("   状态不明确，尝试检测 Start 按钮")

    print("🔌 检测到服务器未运行，尝试点击 Start ...")
    clicked = click_named_button(sb, ["Start", "启动", "play"])
    if not clicked:
        # 左侧绿色播放按钮兜底
        try:
            sb.execute_script(
                """
                var icons = document.querySelectorAll('svg, i, button, div');
                for (var i = 0; i < icons.length; i++) {
                    var el = icons[i];
                    var cls = (el.getAttribute('class') || '').toLowerCase();
                    var html = (el.outerHTML || '').toLowerCase();
                    if (cls.indexOf('play') >= 0 || html.indexOf('fa-play') >= 0) {
                        var clickable = el.closest('button') || el;
                        clickable.click();
                        return true;
                    }
                }
                return false;
                """
            )
        except Exception:
            pass

    time.sleep(5)
    handle_cloudflare(sb)
    for i in range(12):
        info2 = read_panel_info(sb)
        st = (info2.get("status") or "").lower()
        if st == "online" or info2.get("hasStop"):
            print("✅ 服务器已启动")
            return True, "已点击 Start，服务器已在线"
        if st == "starting":
            print("   正在启动中...")
        time.sleep(3)
    print("⚠️ 已尝试启动，但未确认进入 Online")
    return False, "已尝试点击 Start，未确认在线"


def click_renew(sb):
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
        clicked = click_named_button(sb, ["Renew", "续期"])
        if clicked:
            print("✅ 已点击 Renew")
    if not clicked:
        print("❌ 未找到 Renew 按钮")
        safe_screenshot(sb, "renew_not_found.png")
        return False

    time.sleep(3)
    if challenge_visible(sb):
        print("   点击 Renew 后出现验证，正在处理...")
        handle_cloudflare(sb, max_retry=3)
        time.sleep(3)
        click_named_button(sb, ["Renew", "续期"])
        print("   已再次尝试点击 Renew")
    wait_challenge_gone(sb, timeout=15)
    return True


def main():
    if not EMAIL or not PASSWORD:
        print("❌ 请设置环境变量 SKYMC_EMAIL 和 SKYMC_PASSWORD")
        sys.exit(1)

    print("🚀 启动 SkyMC 自动续期脚本 v11")
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

        open_server_panel(sb)
        before = read_panel_info(sb)
        before_time = before.get("remaining")
        print(f"⏱ 续期前剩余时间: {format_remaining(before_time)}")

        started_ok, start_msg = ensure_server_running(sb, before)
        after_start = read_panel_info(sb)

        print("\n📄 开始续期流程...")
        renew_ok = click_renew(sb)

        print("⏳ 等待续期结果刷新...")
        time.sleep(5)
        handle_cloudflare(sb)
        wait_challenge_gone(sb, timeout=15)
        after = read_panel_info(sb)
        after_time = after.get("remaining")
        print(f"⏱ 续期后剩余时间: {format_remaining(after_time)}")

        safe_screenshot(sb, "final_result.png")

        before_min = remaining_to_minutes(before_time)
        after_min = remaining_to_minutes(after_time)
        time_note = "无法对比（有一侧未读到时间）"
        if before_min is not None and after_min is not None:
            delta = after_min - before_min
            if delta > 5:
                time_note = f"倒计时已增加约 {delta} 分钟，续期生效"
            elif delta >= -2:
                time_note = "倒计时变化很小，可能刚续过或尚未刷新"
            else:
                time_note = "倒计时未增加，请人工核对截图"

        status_now = after.get("status") or after_start.get("status") or "unknown"
        lines = [
            f"{'✅' if renew_ok else '❌'} 续期{'已执行' if renew_ok else '失败'}",
            f"服务器: {SERVER_ID}",
            f"当前状态: {status_now}",
            f"启动操作: {start_msg}",
            f"续期前时间: {format_remaining(before_time)}",
            f"续期后时间: {format_remaining(after_time)}",
            f"结论: {time_note}",
            f"IP: {current_ip}",
        ]
        msg = "\n".join(lines)
        print("\n" + msg)
        img = "final_result.png" if os.path.exists("final_result.png") else None
        if not renew_ok and os.path.exists("renew_not_found.png"):
            img = "renew_not_found.png"
        send_tg(TG_BOT_TOKEN, TG_CHAT_ID, msg, image_path=img)

    print("🏁 脚本执行完毕")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SkyMC 自动续期脚本

v11 已能登录、续期、关机启动、读取 MM:SS 倒计时。
v12 新增 NODE_LINK（vless:// 或 vmess://）启动 sing-box 本地代理。
"""

import os
import sys
import time
import json
import atexit
import base64
import shutil
import socket
import subprocess
from urllib.parse import urlparse, parse_qs, unquote
import requests
from seleniumbase import SB

EMAIL = os.environ.get("SKYMC_EMAIL") or os.environ.get("EMAIL") or ""
PASSWORD = os.environ.get("SKYMC_PASSWORD") or os.environ.get("PASSWORD") or ""
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN") or ""
TG_CHAT_ID = os.environ.get("TG_CHAT_ID") or ""

SERVER_URL = os.environ.get("SERVER_URL") or "https://skymc.org/en/server/TuUzR_dWxO2P"
LOGIN_URL = "https://skymc.org/en/login"
SERVER_ID = "TuUzR_dWxO2P"

NODE_LINK = (os.environ.get("NODE_LINK") or "").strip()
IS_PROXY = os.environ.get("IS_PROXY", "false").lower() == "true"
PROXY_SERVER = os.environ.get("PROXY_SERVER") or "socks5://127.0.0.1:7890"
SINGBOX_PORT = int(os.environ.get("SINGBOX_PORT") or "7890")
REQUESTS_PROXIES = {"http": PROXY_SERVER, "https": PROXY_SERVER} if IS_PROXY else None
_SINGBOX_PROC = None

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


def _b64decode(data: str) -> bytes:
    data = data.strip().replace("-", "+").replace("_", "/")
    pad = (-len(data)) % 4
    return base64.b64decode(data + ("=" * pad))


def _parse_vmess(link: str) -> dict:
    raw = link[len("vmess://"):]
    obj = json.loads(_b64decode(raw).decode("utf-8"))
    host = obj.get("add") or obj.get("host") or ""
    port = int(obj.get("port") or 443)
    uuid = obj.get("id") or ""
    net = (obj.get("net") or "tcp").lower()
    tls_on = str(obj.get("tls") or "").lower() in ("tls", "reality", "1", "true")
    sni = obj.get("sni") or obj.get("host") or host
    outbound = {
        "type": "vmess",
        "tag": "proxy",
        "server": host,
        "server_port": port,
        "uuid": uuid,
        "security": obj.get("scy") or "auto",
        "alter_id": int(obj.get("aid") or 0),
    }
    if tls_on:
        outbound["tls"] = {
            "enabled": True,
            "server_name": sni,
            "insecure": False,
            "utls": {"enabled": True, "fingerprint": obj.get("fp") or "chrome"},
        }
    if net == "ws":
        outbound["transport"] = {
            "type": "ws",
            "path": obj.get("path") or "/",
            "headers": {"Host": obj.get("host") or sni or host},
        }
    elif net == "grpc":
        outbound["transport"] = {
            "type": "grpc",
            "service_name": obj.get("path") or obj.get("serviceName") or "",
        }
    return outbound


def _parse_vless(link: str) -> dict:
    parsed = urlparse(link)
    uuid = unquote(parsed.username or "")
    host = parsed.hostname or ""
    port = parsed.port or 443
    q = {k: v[0] for k, v in parse_qs(parsed.query).items()}
    security = (q.get("security") or "none").lower()
    net = (q.get("type") or "tcp").lower()
    outbound = {
        "type": "vless",
        "tag": "proxy",
        "server": host,
        "server_port": int(port),
        "uuid": uuid,
        "flow": q.get("flow") or "",
        "packet_encoding": "xudp",
    }
    if security in ("tls", "reality"):
        tls = {
            "enabled": True,
            "server_name": q.get("sni") or host,
            "utls": {"enabled": True, "fingerprint": q.get("fp") or "chrome"},
        }
        alpn = q.get("alpn")
        if alpn:
            tls["alpn"] = [x.strip() for x in alpn.split(",") if x.strip()]
        if security == "reality":
            tls["reality"] = {
                "enabled": True,
                "public_key": q.get("pbk") or "",
                "short_id": q.get("sid") or "",
            }
        outbound["tls"] = tls
    if net == "ws":
        outbound["transport"] = {
            "type": "ws",
            "path": q.get("path") or "/",
            "headers": {"Host": q.get("host") or q.get("sni") or host},
        }
    elif net == "grpc":
        outbound["transport"] = {
            "type": "grpc",
            "service_name": q.get("serviceName") or q.get("path") or "",
        }
    elif net == "httpupgrade":
        outbound["transport"] = {
            "type": "httpupgrade",
            "path": q.get("path") or "/",
            "headers": {"Host": q.get("host") or q.get("sni") or host},
        }
    return outbound


def build_singbox_config(node_link: str, listen_port: int) -> dict:
    link = node_link.strip()
    if link.startswith("vmess://"):
        outbound = _parse_vmess(link)
    elif link.startswith("vless://"):
        outbound = _parse_vless(link)
    else:
        raise ValueError("NODE_LINK 仅支持 vless:// 或 vmess://")
    if not outbound.get("server") or not outbound.get("uuid"):
        raise ValueError("NODE_LINK 解析失败：缺少 server 或 uuid")
    return {
        "log": {"level": "info", "timestamp": True},
        "inbounds": [
            {
                "type": "mixed",
                "tag": "mixed-in",
                "listen": "127.0.0.1",
                "listen_port": listen_port,
            }
        ],
        "outbounds": [
            outbound,
            {"type": "direct", "tag": "direct"},
        ],
    }


def _port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


def start_singbox_from_node_link():
    """根据 NODE_LINK 启动本地 sing-box，并打开 IS_PROXY。"""
    global IS_PROXY, PROXY_SERVER, REQUESTS_PROXIES, _SINGBOX_PROC
    if not NODE_LINK:
        return
    print("⚙️ 检测到 NODE_LINK，准备启动 sing-box 代理...")
    scheme = NODE_LINK.split("://", 1)[0].lower() if "://" in NODE_LINK else "?"
    print(f"   协议: {scheme}://  本地端口: {SINGBOX_PORT}")

    bin_path = shutil.which("sing-box")
    if not bin_path:
        print("❌ 已设置 NODE_LINK，但系统中找不到 sing-box")
        print("   请确认 GitHub Actions 已安装 sing-box")
        sys.exit(1)

    try:
        cfg = build_singbox_config(NODE_LINK, SINGBOX_PORT)
    except Exception as e:
        print(f"❌ NODE_LINK 解析失败: {e}")
        sys.exit(1)

    cfg_path = "/tmp/sing-box-skymc.json"
    log_path = "/tmp/sing-box-skymc.log"
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

    logf = open(log_path, "ab")
    _SINGBOX_PROC = subprocess.Popen(
        [bin_path, "run", "-c", cfg_path],
        stdout=logf,
        stderr=logf,
    )

    def _stop():
        if _SINGBOX_PROC and _SINGBOX_PROC.poll() is None:
            _SINGBOX_PROC.terminate()
    atexit.register(_stop)

    for _ in range(30):
        if _SINGBOX_PROC.poll() is not None:
            break
        if _port_open("127.0.0.1", SINGBOX_PORT):
            IS_PROXY = True
            PROXY_SERVER = f"socks5://127.0.0.1:{SINGBOX_PORT}"
            REQUESTS_PROXIES = {"http": PROXY_SERVER, "https": PROXY_SERVER}
            print(f"✅ sing-box 已启动，本地代理 {PROXY_SERVER}")
            return
        time.sleep(0.4)

    print("❌ sing-box 启动失败")
    try:
        print(open(log_path, "r", errors="ignore").read()[-3000:])
    except Exception:
        pass
    sys.exit(1)


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


def format_remaining(mmss):
    if not mmss:
        return "未读到"
    parts = str(mmss).split(":")
    try:
        if len(parts) == 2:
            m, s = int(parts[0]), int(parts[1])
            return f"{mmss}（{m}分钟{s}秒）"
        if len(parts) == 3:
            h, m, s = int(parts[0]), int(parts[1]), int(parts[2])
            return f"{mmss}（{h}小时{m}分{s}秒）"
    except Exception:
        pass
    return str(mmss)


def remaining_to_seconds(mmss):
    """面板倒计时为 MM:SS（如 102:18 = 102分钟18秒）"""
    if not mmss:
        return None
    parts = str(mmss).split(":")
    try:
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
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


def wait_until_online(sb, timeout_sec=180, action_label="启动/重启"):
    """必须等到状态为 Online 才算成功。Starting 期间不继续续期。"""
    print(f"⏳ 等待服务器进入 Online（最多 {timeout_sec} 秒）...")
    end = time.time() + timeout_sec
    last_status = ""
    while time.time() < end:
        handle_cloudflare(sb)
        info = read_panel_info(sb)
        st = (info.get("status") or "").lower()
        last_status = st or last_status
        if st == "online":
            # 再等一小会让 Renew 按钮渲染出来
            time.sleep(3)
            info2 = read_panel_info(sb)
            if (info2.get("status") or "").lower() == "online":
                print(f"✅ {action_label}成功，服务器已 Online")
                if info2.get("hasRenew"):
                    print("   Renew 按钮已可用")
                else:
                    print("   提示：Online 但暂未检测到 Renew，稍后仍会尝试点击")
                return True, info2
        if st == "starting":
            print("   仍在 Starting，继续等待...")
        elif st in ("offline", "stopped"):
            print("   当前 Offline/Stopped，继续等待或需再次启动...")
        else:
            print(f"   当前状态: {st or 'unknown'}，继续等待...")
        time.sleep(5)
        # 每 30 秒左右刷新一次面板，避免状态卡住
        if int(time.time()) % 30 < 5:
            try:
                sb.refresh()
                sb.wait_for_ready_state_complete()
                time.sleep(2)
                handle_cloudflare(sb)
            except Exception:
                pass
    print(f"⚠️ 等待超时，最后状态仍为: {last_status or 'unknown'}")
    return False, read_panel_info(sb)


def ensure_server_running(sb, info):
    """
    保证服务器真正 Online 后再返回。
    - Online：直接通过
    - Starting：只等待，不抢点 Renew
    - Offline/Stopped：点 Start，再等到 Online
    - 若需要重启且存在 Restart：可点 Restart 再等到 Online
    """
    status = (info.get("status") or "").lower()
    has_start = info.get("hasStart")
    has_stop = info.get("hasStop")
    has_restart = info.get("hasRestart")

    # 已 Online：直接成功（不要用 hasStop 误判，Starting 时也可能有 Stop）
    if status == "online":
        print("   服务器已 Online，无需启动/重启")
        return True, "已在运行"

    # Starting：只等待到 Online
    if status == "starting":
        print("🔌 服务器正在 Starting，等待启动完成后再续期...")
        ok, _ = wait_until_online(sb, timeout_sec=180, action_label="启动")
        if ok:
            return True, "等待 Starting 完成，服务器已 Online"
        return False, "Starting 超时，未进入 Online"

    # Offline / Stopped / unknown：点 Start
    print(f"🔌 服务器状态为 {status or 'unknown'}，尝试点击 Start ...")
    clicked = click_named_button(sb, ["Start", "启动"])
    if not clicked:
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
            clicked = True
            print("   已通过播放图标尝试启动")
        except Exception:
            pass

    if not clicked and has_restart:
        print("   未找到 Start，尝试 Restart ...")
        clicked = click_named_button(sb, ["Restart", "重启"])
        action = "重启"
    else:
        action = "启动"

    if not clicked and not has_start and status not in ("starting",):
        # 再读一次，可能已经在 Starting
        info2 = read_panel_info(sb)
        if (info2.get("status") or "").lower() == "starting":
            ok, _ = wait_until_online(sb, timeout_sec=180, action_label="启动")
            return (True, "等待 Starting 完成，服务器已 Online") if ok else (False, "Starting 超时，未进入 Online")
        print("⚠️ 未找到 Start/Restart 按钮")
        return False, "未找到 Start/Restart 按钮"

    time.sleep(5)
    handle_cloudflare(sb)
    ok, _ = wait_until_online(sb, timeout_sec=180, action_label=action)
    if ok:
        return True, f"已点击 {action}，服务器已 Online"
    return False, f"已点击 {action}，但等待 Online 超时"


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

    print("🚀 启动 SkyMC 自动续期脚本 v12.1")
    print(f"目标服务器: {SERVER_URL}")

    start_singbox_from_node_link()

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

        if not started_ok:
            print("⚠️ 服务器未进入 Online，跳过续期，避免找不到 Renew")
            safe_screenshot(sb, "final_result.png")
            msg = (
                f"❌ 续期跳过：服务器未 Online\n"
                f"服务器: {SERVER_ID}\n"
                f"当前状态: {(after_start.get('status') or 'unknown')}\n"
                f"启动操作: {start_msg}\n"
                f"续期前时间: {format_remaining(before_time)}\n"
                f"IP: {current_ip}"
            )
            print(msg)
            send_tg(TG_BOT_TOKEN, TG_CHAT_ID, msg, image_path="final_result.png")
            print("🏁 脚本执行完毕")
            return

        # Online 后再确认一次 Renew 是否出现；没有则多等一会儿
        if not after_start.get("hasRenew"):
            print("⏳ Online 但尚未看到 Renew，再等待最多 60 秒...")
            end_wait = time.time() + 60
            while time.time() < end_wait:
                time.sleep(5)
                after_start = read_panel_info(sb)
                if after_start.get("hasRenew") or (after_start.get("status") or "").lower() != "online":
                    break
            if not after_start.get("hasRenew"):
                print("   仍未检测到 Renew 标记，仍将尝试点击")

        print("\n📄 开始续期流程（服务器已 Online）...")
        renew_ok = click_renew(sb)

        print("⏳ 等待续期结果刷新...")
        time.sleep(5)
        handle_cloudflare(sb)
        wait_challenge_gone(sb, timeout=15)
        after = read_panel_info(sb)
        after_time = after.get("remaining")
        print(f"⏱ 续期后剩余时间: {format_remaining(after_time)}")

        safe_screenshot(sb, "final_result.png")

        before_sec = remaining_to_seconds(before_time)
        after_sec = remaining_to_seconds(after_time)
        time_note = "无法对比（有一侧未读到时间）"
        if before_sec is not None and after_sec is not None:
            delta = after_sec - before_sec
            if delta > 30:
                time_note = f"倒计时已增加约 {delta} 秒，续期生效"
            elif delta >= -5:
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

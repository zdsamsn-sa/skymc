#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SkyMC 自动续期脚本 v12

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


def is_activate_server_page(sb):
    """是否处于「Activate Your Server」选套餐页"""
    try:
        text = ""
        try:
            text = sb.execute_script(
                "return (document.body && document.body.innerText) ? document.body.innerText : '';"
            ) or ""
        except Exception:
            text = sb.get_page_source() or ""
        blob = text.lower()
        if "activate your server" in blob:
            return True
        # 备选：有 Plan + COAL Free，且没有面板特征
        if "coal" in blob and "free" in blob and "plan" in blob:
            if "expires in" not in blob and "console" not in blob:
                return True
        return False
    except Exception:
        return False


def click_coal_free(sb):
    """在 Activate 页点击 COAL Free 套餐并进入面板"""
    print("🆓 检测到 Activate Your Server 页面，查找 COAL Free ...")

    # 选择器：卡片/按钮上的 COAL + Free
    selectors = [
        'button:contains("COAL")',
        'div:contains("COAL")',
        '//*[contains(., "COAL") and contains(., "Free")]',
        '//*[contains(translate(., "coal", "COAL"), "COAL")]',
        '//button[contains(., "COAL")]',
        '//div[contains(@class,"card") and contains(., "COAL")]',
    ]
    clicked = False
    for sel in selectors:
        try:
            if sb.is_element_visible(sel):
                try:
                    sb.uc_click(sel)
                except Exception:
                    sb.click(sel)
                print(f"✅ 已点击 COAL 套餐（{sel}）")
                clicked = True
                break
        except Exception:
            continue

    if not clicked:
        try:
            result = sb.execute_script(
                r"""
                var nodes = document.querySelectorAll('button, a, div, section, article, label, span');
                var best = null;
                for (var i = 0; i < nodes.length; i++) {
                    var n = nodes[i];
                    var t = (n.innerText || n.textContent || '').replace(/\s+/g, ' ').trim();
                    if (!t || t.length > 120) continue;
                    // 套餐卡片通常同时含 COAL 与 Free / 3 GB
                    if (!/coal/i.test(t)) continue;
                    if (!(/free/i.test(t) || /3\s*gb/i.test(t))) continue;
                    var r = n.getBoundingClientRect();
                    if (r.width < 40 || r.height < 20) continue;
                    // 优先更小、更像卡片的节点
                    var score = 10000 - (r.width * r.height) / 100;
                    if (/^coal/i.test(t)) score += 500;
                    if (!best || score > best.score) {
                        best = {el: n, text: t.slice(0, 80), score: score, x: r.left+r.width/2, y: r.top+r.height/2};
                    }
                }
                if (!best) return null;
                var target = best.el.closest('button') || best.el.closest('a') || best.el.closest('[role="button"]') || best.el;
                try { target.scrollIntoView({block:'center'}); } catch (e) {}
                try { target.click(); } catch (e) {}
                var opts = {bubbles:true, cancelable:true, view:window, clientX:best.x, clientY:best.y, button:0};
                ['pointerdown','mousedown','pointerup','mouseup','click'].forEach(function(type) {
                    try {
                        var Ev = type.indexOf('pointer')===0 ? PointerEvent : MouseEvent;
                        target.dispatchEvent(new Ev(type, opts));
                    } catch (e) {}
                });
                return best.text;
                """
            )
            if result:
                print(f"✅ 已通过 JS 点击 COAL Free: {result}")
                clicked = True
        except Exception as e:
            print(f"   JS 点击 COAL 失败: {e}")

    if not clicked:
        # CDP 坐标兜底
        try:
            box = sb.execute_script(
                r"""
                var nodes = document.querySelectorAll('button, a, div, section, article');
                for (var i = 0; i < nodes.length; i++) {
                    var n = nodes[i];
                    var t = (n.innerText || '').replace(/\s+/g, ' ').trim();
                    if (!/coal/i.test(t)) continue;
                    if (!(/free/i.test(t) || /3\s*gb/i.test(t))) continue;
                    var r = n.getBoundingClientRect();
                    if (r.width < 40 || r.height < 20) continue;
                    return JSON.stringify({x: r.left+r.width/2, y: r.top+r.height/2, text: t.slice(0,60)});
                }
                return null;
                """
            )
            if box:
                info = json.loads(box)
                print(f"   尝试 CDP 点击 COAL @ ({info['x']:.0f},{info['y']:.0f})")
                if _cdp_click_xy(sb, float(info["x"]), float(info["y"])):
                    clicked = True
                    print("✅ 已 CDP 点击 COAL Free")
        except Exception as e:
            print(f"   CDP 点击 COAL 失败: {e}")

    if not clicked:
        print("❌ 未找到 COAL Free 套餐卡片")
        safe_screenshot(sb, "coal_not_found.png")
        return False

    # 等待进入面板：不再是 Activate 页
    print("⏳ 等待进入服务器面板...")
    time.sleep(3)
    handle_cloudflare(sb)
    for i in range(24):
        if challenge_visible(sb):
            handle_cloudflare(sb, max_retry=2)
        try:
            text = sb.execute_script(
                "return (document.body && document.body.innerText) ? document.body.innerText : '';"
            ) or ""
        except Exception:
            text = ""
        lower = text.lower()
        if "activate your server" not in lower and (
            "expires in" in lower
            or "online" in lower
            or "offline" in lower
            or "stop" in lower
            or "start" in lower
            or "console" in lower
        ):
            print("✅ 已进入服务器面板")
            wait_challenge_gone(sb, timeout=10)
            return True
        # 若仍有 Continue / Confirm / Activate 确认按钮则点一下
        try:
            for label in ("Continue", "Confirm", "Activate", "Create", "Next", "继续", "确认", "激活"):
                sel = f'button:contains("{label}")'
                if sb.is_element_visible(sel):
                    sb.click(sel)
                    print(f"   已点击确认按钮: {label}")
                    time.sleep(2)
                    break
        except Exception:
            pass
        time.sleep(2)

    print("⚠️ 已点击 COAL，但未确认进入面板，继续后续流程")
    safe_screenshot(sb, "after_coal_click.png")
    return True


def ensure_not_on_activate_page(sb):
    """若当前是选套餐页，先选 COAL Free 进入面板"""
    if not is_activate_server_page(sb):
        return True
    return click_coal_free(sb)


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

    # 免费服过期后可能进入 Activate Your Server，需先选 COAL Free
    ensure_not_on_activate_page(sb)
    time.sleep(1)


def read_panel_info(sb):
    """读取状态、剩余时间、可用按钮（含侧边栏 Expires in XXm）"""
    script = r"""
        var body = (document.body && document.body.innerText) ? document.body.innerText : '';
        var status = 'unknown';
        if (/\bOnline\b/i.test(body) || /在线/.test(body)) status = 'Online';
        else if (/\bStarting\b/i.test(body) || /启动中/.test(body)) status = 'Starting';
        else if (/\bStopping\b/i.test(body) || /关闭中/.test(body)) status = 'Stopping';
        else if (/\bOffline\b/i.test(body) || /\bStopped\b/i.test(body) || /离线/.test(body) || /已停止/.test(body)) status = 'Offline';

        var remaining = null;
        // 新 UI：Expires in 59m / Expires in 1h 20m
        var exp = body.match(/Expires\s+in\s+(\d+)\s*h(?:\s*(\d+)\s*m)?/i);
        if (exp) {
            var h = parseInt(exp[1], 10) || 0;
            var m = parseInt(exp[2] || '0', 10) || 0;
            remaining = (h * 60 + m) + 'm';
        } else {
            exp = body.match(/Expires\s+in\s+(\d+)\s*m/i);
            if (exp) {
                remaining = exp[1] + 'm';
            }
        }
        // 兼容旧 UI：MM:SS
        if (!remaining) {
            var matches = body.match(/\b(\d{1,3}:\d{2})\b/g) || [];
            if (matches.length) remaining = matches[0];
        }

        var hasStart = false, hasStop = false, hasRestart = false, hasRenew = false, hasExpires = false;
        var buttons = [];
        var all = document.querySelectorAll('button, a, [role="button"], div, span');
        for (var i = 0; i < all.length; i++) {
            var b = all[i];
            var text = (b.innerText || b.textContent || '').replace(/\s+/g, ' ').trim();
            if (!text || text.length > 80) continue;
            var aria = (b.getAttribute('aria-label') || '') + ' ' + (b.getAttribute('title') || '');
            var html = (b.innerHTML || '').toLowerCase();
            var blob = (text + ' ' + aria).toLowerCase();
            var visible = b.offsetParent !== null;
            if (!visible) continue;
            if (b.tagName === 'BUTTON' || b.getAttribute('role') === 'button') {
                buttons.push({text: text, disabled: !!b.disabled, visible: visible});
            }
            if (b.disabled) continue;
            if (blob.indexOf('start') >= 0 || blob.indexOf('启动') >= 0 || html.indexOf('fa-play') >= 0) hasStart = true;
            if (blob.indexOf('stop') >= 0 || blob.indexOf('停止') >= 0 || blob.indexOf('关机') >= 0) hasStop = true;
            if (blob.indexOf('restart') >= 0 || blob.indexOf('重启') >= 0) hasRestart = true;
            if (blob.indexOf('renew') >= 0 || blob.indexOf('续期') >= 0) hasRenew = true;
            if (blob.indexOf('expires in') >= 0 || blob.indexOf('expire') >= 0) hasExpires = true;
        }
        return JSON.stringify({
            status: status,
            remaining: remaining,
            hasStart: hasStart,
            hasStop: hasStop,
            hasRestart: hasRestart,
            hasRenew: hasRenew,
            hasExpires: hasExpires,
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
          f"Start={info.get('hasStart')} Stop={info.get('hasStop')} "
          f"Expires={info.get('hasExpires')} Renew={info.get('hasRenew')}")
    return info


def format_remaining(val):
    if not val:
        return "未读到"
    s = str(val).strip()
    # 新格式：59m / 120m
    if s.endswith("m") and s[:-1].isdigit():
        mins = int(s[:-1])
        return f"{mins}分钟（Expires in {mins}m）"
    parts = s.split(":")
    try:
        if len(parts) == 2:
            m, sec = int(parts[0]), int(parts[1])
            return f"{s}（{m}分钟{sec}秒）"
        if len(parts) == 3:
            h, m, sec = int(parts[0]), int(parts[1]), int(parts[2])
            return f"{s}（{h}小时{m}分{sec}秒）"
    except Exception:
        pass
    return s


def remaining_to_seconds(val):
    """支持 59m 或 MM:SS"""
    if not val:
        return None
    s = str(val).strip().lower()
    try:
        if s.endswith("m") and s[:-1].isdigit():
            return int(s[:-1]) * 60
        parts = s.split(":")
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


def _is_visible_box(rect):
    return rect and rect.get("w", 0) > 5 and rect.get("h", 0) > 5


def locate_expires_button(sb):
    """只返回真正可见、有尺寸的 Expires 按钮信息"""
    try:
        info = sb.execute_script(
            r"""
            var best = null;
            var nodes = document.querySelectorAll('button, a, [role="button"]');
            for (var i = 0; i < nodes.length; i++) {
                var n = nodes[i];
                var t = (n.innerText || n.textContent || '').replace(/\s+/g, ' ').trim();
                if (!/expires\s+in\s+\d+/i.test(t)) continue;
                var r = n.getBoundingClientRect();
                if (r.width < 5 || r.height < 5) continue;
                var st = window.getComputedStyle(n);
                if (st.display === 'none' || st.visibility === 'hidden' || st.opacity === '0') continue;
                // 侧边栏底部按钮通常在左下角
                var score = r.bottom + (r.left < 400 ? 1000 : 0);
                var item = {
                    text: t,
                    x: r.left + r.width / 2,
                    y: r.top + r.height / 2,
                    w: r.width,
                    h: r.height,
                    left: r.left,
                    top: r.top,
                    ariaExpanded: n.getAttribute('aria-expanded'),
                    dataState: n.getAttribute('data-state'),
                    className: (n.className || '').toString().slice(0, 120),
                    tag: n.tagName,
                    score: score
                };
                if (!best || item.score > best.score) best = item;
            }
            return best ? JSON.stringify(best) : null;
            """
        )
        if not info:
            return None
        return json.loads(info)
    except Exception as e:
        print(f"   locate_expires 失败: {e}")
        return None


def locate_renew_option(sb):
    try:
        info = sb.execute_script(
            r"""
            var best = null;
            var nodes = document.querySelectorAll('button, a, [role="menuitem"], [role="option"], li, div, span');
            for (var i = 0; i < nodes.length; i++) {
                var n = nodes[i];
                var t = (n.innerText || n.textContent || '').replace(/\s+/g, ' ').trim();
                if (!(/^renew$/i.test(t) || t === '续期')) continue;
                if (/expires/i.test(t)) continue;
                var r = n.getBoundingClientRect();
                if (r.width < 3 || r.height < 3) continue;
                var st = window.getComputedStyle(n);
                if (st.display === 'none' || st.visibility === 'hidden') continue;
                best = {
                    text: t,
                    x: r.left + r.width / 2,
                    y: r.top + r.height / 2,
                    w: r.width,
                    h: r.height,
                    role: n.getAttribute('role'),
                    tag: n.tagName
                };
                break;
            }
            return best ? JSON.stringify(best) : null;
            """
        )
        if not info:
            return None
        return json.loads(info)
    except Exception:
        return None


def renew_visible_in_dom(sb):
    return locate_renew_option(sb) is not None


def _cdp_click_xy(sb, x, y):
    """用 CDP 在视口坐标点击（比 JS click 更接近真实用户）"""
    try:
        driver = sb.driver
        driver.execute_cdp_cmd(
            "Input.dispatchMouseEvent",
            {"type": "mouseMoved", "x": x, "y": y, "button": "none", "buttons": 0},
        )
        time.sleep(0.05)
        for etype in ("mousePressed", "mouseReleased"):
            driver.execute_cdp_cmd(
                "Input.dispatchMouseEvent",
                {
                    "type": etype,
                    "x": x,
                    "y": y,
                    "button": "left",
                    "buttons": 1 if etype == "mousePressed" else 0,
                    "clickCount": 1,
                },
            )
            time.sleep(0.05)
        return True
    except Exception as e:
        print(f"   CDP 点击失败: {e}")
        return False


def _action_chains_click_expires(sb):
    """Selenium ActionChains：移动到可见 Expires 按钮再点击"""
    try:
        from selenium.webdriver.common.action_chains import ActionChains
        from selenium.webdriver.common.keys import Keys
        from selenium.webdriver.common.by import By

        candidates = sb.driver.find_elements(
            By.XPATH,
            "//button[contains(., 'Expires in')] | //*[@role='button' and contains(., 'Expires in')]",
        )
        target = None
        for el in candidates:
            try:
                if not el.is_displayed():
                    continue
                size = el.size
                if size.get("width", 0) < 5 or size.get("height", 0) < 5:
                    continue
                target = el
                # 偏好更靠下的（侧边栏底部）
            except Exception:
                continue
        if not target:
            return False

        sb.driver.execute_script(
            "arguments[0].scrollIntoView({block:'center', inline:'center'});", target
        )
        time.sleep(0.3)
        actions = ActionChains(sb.driver)
        actions.move_to_element(target).pause(0.4).click(target).perform()
        print("   ActionChains 已 hover+click Expires")
        time.sleep(1.0)
        if renew_visible_in_dom(sb):
            return True

        # 键盘：Space / Enter 打开菜单
        try:
            target.send_keys(Keys.SPACE)
            time.sleep(0.8)
            if renew_visible_in_dom(sb):
                print("   通过 Space 打开菜单")
                return True
            target.send_keys(Keys.ENTER)
            time.sleep(0.8)
            if renew_visible_in_dom(sb):
                print("   通过 Enter 打开菜单")
                return True
            target.send_keys(Keys.ARROW_DOWN)
            time.sleep(0.8)
            if renew_visible_in_dom(sb):
                print("   通过 ArrowDown 打开菜单")
                return True
        except Exception as e:
            print(f"   键盘打开菜单失败: {e}")
        return renew_visible_in_dom(sb)
    except Exception as e:
        print(f"   ActionChains 失败: {e}")
        return False


def open_expires_menu(sb):
    """点击侧边栏「Expires in XXm」，并确认菜单已打开（出现 Renew）"""
    print("🔍 查找并点击侧边栏 Expires 入口...")

    info = locate_expires_button(sb)
    if info:
        print(
            f"   定位到 Expires: text={info.get('text')} pos=({info.get('x'):.0f},{info.get('y'):.0f}) "
            f"size={info.get('w'):.0f}x{info.get('h'):.0f} "
            f"aria-expanded={info.get('ariaExpanded')} data-state={info.get('dataState')}"
        )
    else:
        print("   ⚠️ 未定位到可见的 Expires 按钮")

    # 方法 1：ActionChains hover + click + 键盘
    if _action_chains_click_expires(sb):
        print("✅ Expires 菜单已打开（ActionChains）")
        return True

    # 方法 2：CDP 坐标点击
    info = locate_expires_button(sb)
    if info and _is_visible_box(info):
        x, y = float(info["x"]), float(info["y"])
        print(f"   尝试 CDP 坐标点击 ({x:.0f}, {y:.0f})")
        _cdp_click_xy(sb, x, y)
        time.sleep(1.2)
        if renew_visible_in_dom(sb):
            print("✅ Expires 菜单已打开（CDP）")
            return True
        # 再点一次稍偏上一点（有的热区在图标处）
        _cdp_click_xy(sb, x, y - 5)
        time.sleep(1.0)
        if renew_visible_in_dom(sb):
            print("✅ Expires 菜单已打开（CDP 偏移）")
            return True

    # 方法 3：SeleniumBase uc_click / click
    for sel in [
        'button:contains("Expires in")',
        '//button[contains(., "Expires in")]',
    ]:
        try:
            if sb.is_element_visible(sel):
                try:
                    sb.uc_click(sel)
                except Exception:
                    sb.click(sel)
                print(f"   已 uc/click Expires（{sel}）")
                time.sleep(1.2)
                if renew_visible_in_dom(sb):
                    print("✅ Expires 菜单已打开（uc_click）")
                    return True
        except Exception:
            continue

    # 方法 4：JS 在「可见」按钮上派发完整指针事件
    try:
        hit = sb.execute_script(
            r"""
            var nodes = document.querySelectorAll('button, a, [role="button"]');
            var target = null;
            var bestBottom = -1;
            for (var i = 0; i < nodes.length; i++) {
                var n = nodes[i];
                var t = (n.innerText || '').replace(/\s+/g, ' ').trim();
                if (!/expires\s+in\s+\d+/i.test(t)) continue;
                var r = n.getBoundingClientRect();
                if (r.width < 5 || r.height < 5) continue;
                if (r.bottom > bestBottom) { bestBottom = r.bottom; target = n; }
            }
            if (!target) return null;
            target.scrollIntoView({block:'center'});
            target.focus();
            var r = target.getBoundingClientRect();
            var x = r.left + r.width/2, y = r.top + r.height/2;
            var opts = {bubbles:true, cancelable:true, view:window, clientX:x, clientY:y, button:0, pointers:1};
            ['pointerover','pointerenter','mouseover','mouseenter','pointerdown','mousedown',
             'pointerup','mouseup','click'].forEach(function(type) {
                try {
                    var Ev = type.indexOf('pointer') === 0 ? PointerEvent : MouseEvent;
                    target.dispatchEvent(new Ev(type, opts));
                } catch (e) {
                    try { target.dispatchEvent(new MouseEvent(type, opts)); } catch (e2) {}
                }
            });
            try { target.click(); } catch (e) {}
            return (target.innerText || '').replace(/\s+/g,' ').trim();
            """
        )
        if hit:
            print(f"   已 JS 完整事件点击: {hit}")
            time.sleep(1.5)
            if renew_visible_in_dom(sb):
                print("✅ Expires 菜单已打开（JS events）")
                return True
    except Exception as e:
        print(f"   JS events 点击失败: {e}")

    # 最后再轮询一会儿
    for _ in range(10):
        if renew_visible_in_dom(sb):
            print("✅ Expires 菜单已打开（延迟检测到）")
            return True
        time.sleep(0.4)

    print("   ⚠️ 多次点击后仍未看到 Renew 菜单项")
    return False


def click_renew_option(sb):
    """在已打开的菜单中点击 Renew"""
    info = locate_renew_option(sb)
    if info and _is_visible_box(info):
        print(f"   定位到 Renew: {info.get('text')} @ ({info.get('x'):.0f},{info.get('y'):.0f})")
        if _cdp_click_xy(sb, float(info["x"]), float(info["y"])):
            time.sleep(0.8)
            print("✅ 已 CDP 点击 Renew")
            return True

    for sel in [
        'button:contains("Renew")',
        'a:contains("Renew")',
        '//button[normalize-space()="Renew"]',
        '//*[@role="menuitem" and contains(., "Renew")]',
        '//*[normalize-space()="Renew"]',
        'button:contains("续期")',
    ]:
        try:
            if sb.is_element_visible(sel):
                try:
                    sb.uc_click(sel)
                except Exception:
                    sb.click(sel)
                print(f"✅ 已点击 Renew（{sel}）")
                return True
        except Exception:
            continue

    # ActionChains 点 Renew
    try:
        from selenium.webdriver.common.action_chains import ActionChains
        from selenium.webdriver.common.by import By

        els = sb.driver.find_elements(
            By.XPATH,
            "//*[normalize-space()='Renew' or normalize-space()='续期']",
        )
        for el in els:
            try:
                if not el.is_displayed():
                    continue
                ActionChains(sb.driver).move_to_element(el).pause(0.2).click(el).perform()
                print("✅ 已 ActionChains 点击 Renew")
                return True
            except Exception:
                continue
    except Exception as e:
        print(f"   ActionChains 点 Renew 失败: {e}")

    return False


def dump_menu_debug(sb):
    try:
        info = sb.execute_script(
            r"""
            var out = [];
            var nodes = document.querySelectorAll('button, a, [role="menuitem"], [role="menu"], [role="listbox"], li, div, span');
            for (var i = 0; i < nodes.length && out.length < 50; i++) {
                var t = (nodes[i].innerText || '').replace(/\s+/g, ' ').trim();
                if (!t || t.length > 60) continue;
                if (!/renew|upgrade|expire|续期|升级/i.test(t)) continue;
                var r = nodes[i].getBoundingClientRect();
                out.push({
                    tag: nodes[i].tagName,
                    role: nodes[i].getAttribute('role'),
                    text: t.slice(0, 40),
                    visible: nodes[i].offsetParent !== null,
                    ariaExpanded: nodes[i].getAttribute('aria-expanded'),
                    dataState: nodes[i].getAttribute('data-state'),
                    w: Math.round(r.width),
                    h: Math.round(r.height)
                });
            }
            return JSON.stringify(out);
            """
        )
        print("   菜单相关 DOM:", info)
        exp = locate_expires_button(sb)
        if exp:
            print("   Expires 按钮详情:", json.dumps(exp, ensure_ascii=False))
    except Exception as e:
        print("   dump_menu_debug 失败:", e)


def click_renew(sb):
    """
    流程：
      1. 点侧边栏 Expires in XXm
      2. 等待菜单出现 Renew
      3. 点击 Renew
      4. 若弹出 Cloudflare，按原逻辑处理
    """
    print("🔍 开始续期：Expires → 等待 Renew → 点击 Renew...")

    # 旧 UI：页面上直接有 Renew
    for sel in ['button:contains("Renew")', 'button:contains("续期")']:
        try:
            if sb.is_element_visible(sel):
                # 排除侧边栏还没打开菜单时误点（旧面板大按钮）
                sb.uc_click(sel)
                print(f"✅ 直接点击 Renew 成功（{sel}）")
                time.sleep(3)
                if challenge_visible(sb):
                    print("   出现验证，处理中...")
                    handle_cloudflare(sb, max_retry=4)
                    time.sleep(2)
                wait_challenge_gone(sb, timeout=20)
                return True
        except Exception:
            continue

    # 新 UI：最多重试 3 次打开菜单并点 Renew
    for attempt in range(1, 4):
        print(f"   第 {attempt} 次尝试打开 Expires 菜单...")
        opened = open_expires_menu(sb)

        # 即使 open 返回 False，也再轮询等 Renew 出现
        if not renew_visible_in_dom(sb):
            print("   等待菜单中出现 Renew（最多 10 秒）...")
            for _ in range(20):
                if renew_visible_in_dom(sb):
                    opened = True
                    break
                time.sleep(0.5)

        if not renew_visible_in_dom(sb):
            print(f"   第 {attempt} 次未出现 Renew，准备重试...")
            dump_menu_debug(sb)
            # 点一下页面空白，关掉可能的半开状态，再试
            try:
                sb.execute_script("document.body.click();")
            except Exception:
                pass
            time.sleep(1)
            continue

        print("✅ 已检测到 Renew，准备点击...")
        if click_renew_option(sb):
            time.sleep(3)
            if challenge_visible(sb):
                print("   点击 Renew 后出现验证，正在处理...")
                handle_cloudflare(sb, max_retry=4)
                time.sleep(3)
                # 验证过后若菜单还在，再点一次 Renew
                if renew_visible_in_dom(sb):
                    print("   验证后菜单仍在，再次点击 Renew...")
                    click_renew_option(sb)
                    time.sleep(2)
            wait_challenge_gone(sb, timeout=20)
            return True

        print("   检测到 Renew 但点击失败，重试...")
        dump_menu_debug(sb)
        time.sleep(1)

    print("❌ 多次尝试后仍无法点击 Renew")
    dump_menu_debug(sb)
    safe_screenshot(sb, "renew_not_found.png")
    return False


def main():
    if not EMAIL or not PASSWORD:
        print("❌ 请设置环境变量 SKYMC_EMAIL 和 SKYMC_PASSWORD")
        sys.exit(1)

    print("🚀 启动 SkyMC 自动续期脚本 v12.5")
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

        # Online 后确认侧边栏 Expires 入口（新 UI 的续期入口）
        if not after_start.get("hasExpires") and not after_start.get("hasRenew"):
            print("⏳ Online 但尚未看到 Expires/Renew 入口，再等待最多 60 秒...")
            end_wait = time.time() + 60
            while time.time() < end_wait:
                time.sleep(5)
                after_start = read_panel_info(sb)
                if after_start.get("hasExpires") or after_start.get("hasRenew"):
                    break
            if not after_start.get("hasExpires") and not after_start.get("hasRenew"):
                print("   仍未检测到 Expires/Renew，仍将尝试点击")

        print("\n📄 开始续期流程（服务器已 Online）...")
        print("   入口：侧边栏 Expires in XXm → 菜单 Renew")
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

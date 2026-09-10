#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SkyMC 免费服务器自动续期脚本 v3
增加：模拟点击 Cloudflare「Verify you are human」验证
"""

import os
import time
import sys
import random
import requests
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# ==================== 配置区域 ====================
EMAIL = os.getenv("SKYMC_EMAIL", "你的邮箱@example.com")
PASSWORD = os.getenv("SKYMC_PASSWORD", "你的密码")
SERVER_URL = "https://skymc.org/en/server/TuUzR_dWxO2P"
HEADLESS = os.getenv("HEADLESS", "true").lower() == "true"

TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "")
TG_CHAT_ID = os.getenv("TG_CHAT_ID", "")
# =================================================


def send_telegram(text: str, photo_path: str = None):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        print("⚠️  未配置 TG_BOT_TOKEN 或 TG_CHAT_ID，跳过 Telegram 通知")
        return False
    try:
        if photo_path and os.path.exists(photo_path):
            url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendPhoto"
            with open(photo_path, "rb") as f:
                files = {"photo": f}
                data = {"chat_id": TG_CHAT_ID, "caption": text, "parse_mode": "HTML"}
                resp = requests.post(url, data=data, files=files, timeout=30)
        else:
            url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
            payload = {
                "chat_id": TG_CHAT_ID,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True
            }
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


def human_delay(min_s=0.3, max_s=1.2):
    time.sleep(random.uniform(min_s, max_s))


def try_click_cloudflare(page):
    """尝试模拟点击 Cloudflare 验证框"""
    print("🛡️  检测到 Cloudflare 验证，尝试模拟点击...")

    # 多种可能的选择器
    selectors = [
        'input[type="checkbox"]',
        '#cf-turnstile',
        'iframe[src*="challenges.cloudflare.com"]',
        'iframe[src*="turnstile"]',
        '.cf-turnstile',
        '[data-sitekey]',
        'label:has-text("Verify you are human")',
        'div:has-text("Verify you are human")',
        'span:has-text("Verify you are human")',
        'label.cb-lb',
        '#challenge-stage',
        'input[name="cf-turnstile-response"]',
    ]

    clicked = False

    # 1. 尝试直接点击 checkbox
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if loc.count() > 0 and loc.is_visible(timeout=3000):
                print(f"   找到元素: {sel}")
                # 模拟人类鼠标移动再点击
                box = loc.bounding_box()
                if box:
                    page.mouse.move(
                        box["x"] + box["width"] / 2 + random.uniform(-5, 5),
                        box["y"] + box["height"] / 2 + random.uniform(-5, 5)
                    )
                    human_delay(0.2, 0.6)
                loc.click(timeout=5000, force=True)
                clicked = True
                print("   ✅ 已尝试点击验证框")
                break
        except Exception as e:
            continue

    # 2. 如果有 iframe，尝试进入 iframe 点击
    if not clicked:
        try:
            frames = page.frames
            for frame in frames:
                if "cloudflare" in frame.url or "turnstile" in frame.url or "challenges" in frame.url:
                    print(f"   进入 Cloudflare iframe: {frame.url[:60]}...")
                    try:
                        checkbox = frame.locator('input[type="checkbox"], .cb-lb, body').first
                        if checkbox.count() > 0:
                            checkbox.click(timeout=5000, force=True)
                            clicked = True
                            print("   ✅ 已在 iframe 内点击")
                            break
                    except:
                        # 尝试点击 iframe 中心
                        try:
                            frame.click("body", timeout=3000)
                            clicked = True
                            print("   ✅ 已点击 iframe body")
                            break
                        except:
                            pass
        except Exception as e:
            print(f"   iframe 处理异常: {e}")

    # 3. 等待验证结果
    if clicked:
        print("   等待 Cloudflare 验证结果（最多 15 秒）...")
        for i in range(15):
            time.sleep(1)
            content = page.content().lower()
            if "security verification" not in content and "verify you are human" not in content:
                print("   ✅ Cloudflare 验证似乎已通过！")
                return True
            # 有时会出现成功提示
            if "success" in content or "verified" in content:
                print("   ✅ 检测到验证成功标志")
                return True
        print("   ⚠️  等待超时，验证可能未通过")
        return False
    else:
        print("   ❌ 未找到可点击的验证元素")
        return False


def renew_server():
    print("=" * 55)
    print("SkyMC 免费服务器自动续期脚本 v3")
    print(f"目标服务器：{SERVER_URL}")
    print("=" * 55)

    with sync_playwright() as p:
        # 使用更真实的启动参数，降低被检测概率
        browser = p.chromium.launch(
            headless=HEADLESS,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--window-size=1280,800",
            ]
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            locale="en-US",
            timezone_id="Asia/Shanghai",
            java_script_enabled=True,
        )

        # 隐藏 webdriver 特征
        page = context.new_page()
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            window.chrome = { runtime: {} };
        """)

        try:
            # 1. 打开登录页
            print("\n[1/6] 正在打开登录页面...")
            page.goto("https://skymc.org/en/login", timeout=60000, wait_until="domcontentloaded")
            human_delay(2, 4)

            # 2. 检测并处理 Cloudflare
            content = page.content().lower()
            if "security verification" in content or "verify you are human" in content or "cf-turnstile" in content:
                page.screenshot(path="cloudflare_before.png")
                success = try_click_cloudflare(page)
                page.screenshot(path="cloudflare_after.png")

                if not success:
                    send_telegram(
                        "❌ <b>SkyMC 自动续期失败</b>\n\nCloudflare 验证未能自动通过。\n请手动登录面板点击 Renew。\n\n面板：https://skymc.org/en/server/TuUzR_dWxO2P",
                        "cloudflare_after.png"
                    )
                    print("❌ Cloudflare 验证失败，终止脚本")
                    sys.exit(1)
                human_delay(2, 3)

            # 3. 输入账号密码
            print("[2/6] 正在输入账号密码...")
            email_selectors = [
                'input[type="email"]',
                'input[name="email"]',
                'input[placeholder*="Email" i]',
                'input[placeholder*="Username" i]',
                'input[type="text"]'
            ]
            password_selectors = [
                'input[type="password"]',
                'input[name="password"]'
            ]

            email_filled = False
            for sel in email_selectors:
                try:
                    if page.locator(sel).count() > 0:
                        page.fill(sel, EMAIL, timeout=5000)
                        email_filled = True
                        human_delay()
                        break
                except:
                    continue
            if not email_filled:
                raise Exception("无法找到邮箱输入框")

            for sel in password_selectors:
                try:
                    if page.locator(sel).count() > 0:
                        page.fill(sel, PASSWORD, timeout=5000)
                        human_delay()
                        break
                except:
                    continue

            # 4. 点击登录
            print("[3/6] 正在点击登录...")
            login_selectors = [
                'button:has-text("Login")',
                'button:has-text("Sign in")',
                'button:has-text("Log in")',
                'button[type="submit"]'
            ]
            clicked = False
            for sel in login_selectors:
                try:
                    if page.locator(sel).count() > 0:
                        page.click(sel, timeout=5000)
                        clicked = True
                        break
                except:
                    continue
            if not clicked:
                raise Exception("无法找到登录按钮")

            page.wait_for_load_state("networkidle", timeout=30000)
            human_delay(3, 5)

            # 再次检查是否还在验证或登录页
            content = page.content().lower()
            current_url = page.url.lower()
            if "security verification" in content or "verify you are human" in content:
                print("⚠️  登录后仍出现 Cloudflare 验证，再次尝试...")
                try_click_cloudflare(page)
                human_delay(3, 5)
                content = page.content().lower()

            if "login" in current_url and ("security verification" in content or "verify you are human" in content):
                page.screenshot(path="login_failed.png")
                send_telegram(
                    "⚠️ <b>SkyMC 自动续期 - 登录失败</b>\n\n可能原因：\n1. 账号密码错误\n2. Cloudflare 验证未通过\n\n请手动登录：https://skymc.org/en/server/TuUzR_dWxO2P",
                    "login_failed.png"
                )
                print("已保存截图：login_failed.png")
                sys.exit(1)

            # 5. 进入服务器面板
            print("[4/6] 正在进入服务器面板...")
            page.goto(SERVER_URL, timeout=60000, wait_until="domcontentloaded")
            human_delay(2, 4)

            # 6. 点击 Renew
            print("[5/6] 正在查找并点击 Renew 按钮...")
            renew_selectors = [
                'button:has-text("Renew")',
                'button:has-text("续期")',
                'button >> text=/Renew/i'
            ]

            renew_clicked = False
            for sel in renew_selectors:
                try:
                    locator = page.locator(sel).first
                    if locator.is_visible(timeout=8000):
                        locator.click()
                        renew_clicked = True
                        print("✅ 成功点击 Renew 按钮！")
                        break
                except:
                    continue

            print("[6/6] 处理结果...")
            if renew_clicked:
                human_delay(2, 3)
                page.screenshot(path="renew_success.png")
                send_telegram(
                    "✅ <b>SkyMC 自动续期成功</b>\n\n已成功点击 Renew 按钮。\n服务器：TuUzR_dWxO2P",
                    "renew_success.png"
                )
                print("✅ 续期成功，截图已发送到 Telegram")
            else:
                print("❌ 未找到 Renew 按钮")
                page.screenshot(path="renew_not_found.png")
                send_telegram(
                    "❌ <b>SkyMC 自动续期 - 未找到 Renew 按钮</b>\n\n可能原因：\n1. 刚刚已经续期过\n2. 页面结构变化\n3. 需要先启动服务器\n\n请手动检查：https://skymc.org/en/server/TuUzR_dWxO2P",
                    "renew_not_found.png"
                )
                print("已保存截图：renew_not_found.png")

        except Exception as e:
            print(f"\n❌ 发生错误：{e}")
            try:
                page.screenshot(path="error.png")
                send_telegram(f"❌ <b>SkyMC 自动续期异常</b>\n\n错误信息：{e}", "error.png")
            except:
                pass
            sys.exit(1)
        finally:
            browser.close()


if __name__ == "__main__":
    if EMAIL == "你的邮箱@example.com" or PASSWORD == "你的密码":
        print("⚠️  请先设置 SKYMC_EMAIL 和 SKYMC_PASSWORD 环境变量！")
        sys.exit(1)
    renew_server()

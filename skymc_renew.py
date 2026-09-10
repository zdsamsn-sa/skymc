#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SkyMC 免费服务器自动续期脚本
功能：登录面板 → 自动点击 Renew 按钮
适用：本地运行 或 GitHub Actions
"""

import os
import time
import sys
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# ==================== 配置区域 ====================
# 优先读取环境变量（GitHub Actions Secrets），本地可直接修改下面两行
EMAIL = os.getenv("SKYMC_EMAIL", "你的邮箱@example.com")
PASSWORD = os.getenv("SKYMC_PASSWORD", "你的密码")
SERVER_URL = "https://skymc.org/en/server/TuUzR_dWxO2P"
HEADLESS = os.getenv("HEADLESS", "true").lower() == "true"  # GitHub Actions 用 true，本地调试可改 false
# =================================================


def renew_server():
    print("=" * 50)
    print("SkyMC 免费服务器自动续期脚本启动")
    print(f"目标服务器：{SERVER_URL}")
    print("=" * 50)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=HEADLESS,
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="en-US"
        )
        page = context.new_page()

        try:
            # 1. 打开登录页
            print("\n[1/5] 正在打开登录页面...")
            page.goto("https://skymc.org/en/login", timeout=60000)
            page.wait_for_load_state("domcontentloaded")
            time.sleep(2)

            # 2. 输入账号密码
            print("[2/5] 正在输入账号密码...")
            # 尝试多种可能的选择器
            email_selectors = [
                'input[type="email"]',
                'input[name="email"]',
                'input[placeholder*="Email" i]',
                'input[placeholder*="Username" i]',
                'input[placeholder*="email" i]',
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
                        break
                except:
                    continue

            if not email_filled:
                raise Exception("无法找到邮箱输入框，页面结构可能已变化")

            for sel in password_selectors:
                try:
                    if page.locator(sel).count() > 0:
                        page.fill(sel, PASSWORD, timeout=5000)
                        break
                except:
                    continue

            # 点击登录
            print("[3/5] 正在点击登录...")
            login_selectors = [
                'button:has-text("Login")',
                'button:has-text("Sign in")',
                'button:has-text("Log in")',
                'button[type="submit"]',
                'button:has-text("登录")'
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
            time.sleep(3)

            # 检查是否登录成功（简单判断）
            if "login" in page.url.lower():
                print("⚠️  警告：可能仍在登录页面，请检查账号密码是否正确")
                page.screenshot(path="login_failed.png")
                print("已保存截图：login_failed.png")

            # 4. 进入服务器面板
            print("[4/5] 正在进入服务器面板...")
            page.goto(SERVER_URL, timeout=60000)
            page.wait_for_load_state("domcontentloaded")
            time.sleep(3)

            # 5. 点击 Renew 按钮
            print("[5/5] 正在查找并点击 Renew 按钮...")
            renew_selectors = [
                'button:has-text("Renew")',
                'button:has-text("续期")',
                'button:has-text("renew")',
                '[class*="renew" i]',
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
                except PlaywrightTimeoutError:
                    continue
                except Exception as e:
                    print(f"尝试选择器 {sel} 失败: {e}")
                    continue

            if not renew_clicked:
                print("❌ 未找到可点击的 Renew 按钮")
                print("可能原因：")
                print("  1. 刚刚已经续期过，按钮暂时消失")
                print("  2. 页面结构变化")
                print("  3. 需要先启动服务器")
                page.screenshot(path="renew_not_found.png")
                print("已保存截图：renew_not_found.png")
            else:
                time.sleep(4)
                page.screenshot(path="renew_success.png")
                print("✅ 续期操作完成，已保存截图：renew_success.png")

            print("\n脚本执行结束")

        except Exception as e:
            print(f"\n❌ 发生错误：{e}")
            try:
                page.screenshot(path="error.png")
                print("已保存错误截图：error.png")
            except:
                pass
            sys.exit(1)
        finally:
            browser.close()


if __name__ == "__main__":
    if EMAIL == "你的邮箱@example.com" or PASSWORD == "你的密码":
        print("⚠️  请先设置 SKYMC_EMAIL 和 SKYMC_PASSWORD 环境变量，或修改脚本内的账号密码！")
        sys.exit(1)
    renew_server()

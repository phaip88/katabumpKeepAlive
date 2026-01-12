#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KataBump 自动续订/提醒脚本 - 最终修正版
基于用户登录成功版优化：增强日期抓取 + 强制续订触发
"""

import os
import sys
import re
import requests
from datetime import datetime, timezone, timedelta

# 配置
DASHBOARD_URL = 'https://dashboard.katabump.com'
SERVER_ID = os.environ.get('KATA_SERVER_ID', '201692')
KATA_EMAIL = os.environ.get('KATA_EMAIL', '')
KATA_PASSWORD = os.environ.get('KATA_PASSWORD', '')
TG_BOT_TOKEN = os.environ.get('TG_BOT_TOKEN', '')
TG_CHAT_ID = os.environ.get('TG_USER_ID', '') # 请确保 GitHub Secret 名为 TG_USER_ID

# 执行器配置
EXECUTOR_NAME = os.environ.get('EXECUTOR_NAME', 'GitHub Actions')

def log(msg):
    tz = timezone(timedelta(hours=8))
    t = datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S')
    print(f'[{t}] {msg}')

def send_telegram(message):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        log('⚠️ 未配置 TG 变量，跳过通知')
        return False
    try:
        requests.post(
            f'https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage',
            json={'chat_id': TG_CHAT_ID, 'text': message, 'parse_mode': 'HTML'},
            timeout=30
        )
        log('✅ Telegram 通知已发送')
        return True
    except Exception as e:
        log(f'❌ Telegram 错误: {e}')
    return False

def get_expiry(html):
    # 修正：更强大的日期抓取正则，防止返回 None
    patterns = [
        r'Expiry[\s\S]*?(\d{4}-\d{2}-\d{2})',
        r'(\d{4}-\d{2}-\d{2})'
    ]
    for p in patterns:
        match = re.search(p, html, re.IGNORECASE)
        if match: return match.group(1)
    return None

def get_csrf(html):
    patterns = [
        r'<input[^>]*name=["\']csrf["\'][^>]*value=["\']([^"\']+)["\']',
        r'<input[^>]*value=["\']([^"\']+)["\'][^>]*name=["\']csrf["\']',
    ]
    for p in patterns:
        m = re.search(p, html, re.IGNORECASE)
        if m and len(m.group(1)) > 10:
            return m.group(1)
    return None

def days_until(date_str):
    try:
        if not date_str or date_str == '未知': return None
        exp = datetime.strptime(date_str, '%Y-%m-%d')
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        return (exp - today).days
    except:
        return None

def run():
    log(f'🚀 开始执行 - 服务器 ID: {SERVER_ID}')
    session = requests.Session()
    # 保留你原本成功的 Headers
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    })
    
    try:
        # ========== 1. 登录 (保留原逻辑) ==========
        log('🔐 登录中...')
        session.get(f'{DASHBOARD_URL}/auth/login', timeout=30)
        login_resp = session.post(
            f'{DASHBOARD_URL}/auth/login',
            data={'email': KATA_EMAIL, 'password': KATA_PASSWORD, 'remember': 'true'},
            headers={'Content-Type': 'application/x-www-form-urlencoded', 'Referer': f'{DASHBOARD_URL}/auth/login'},
            timeout=30, allow_redirects=True
        )
        if '/auth/login' in login_resp.url: raise Exception('登录失败')
        log('✅ 登录成功')
        
        # ========== 2. 获取服务器信息 ==========
        server_page = session.get(f'{DASHBOARD_URL}/servers/edit?id={SERVER_ID}', timeout=30)
        expiry = get_expiry(server_page.text) or '未知'
        days = days_until(expiry)
        csrf = get_csrf(server_page.text)
        log(f'📅 到期: {expiry} (剩余 {days if days is not None else "未知"} 天)')
        
        # ========== 3. 尝试续订 ==========
        # 修正：即使日期是未知，或者剩余天数小于等于 2 天，都强制尝试
        if days is None or days <= 2:
            log('🔄 满足触发条件，正在发送 API 续订请求...')
            api_resp = session.post(
                f'{DASHBOARD_URL}/api-client/renew?id={SERVER_ID}',
                data={'csrf': csrf} if csrf else {},
                headers={'Referer': f'{DASHBOARD_URL}/servers/edit?id={SERVER_ID}'},
                timeout=30, allow_redirects=False # 重要：禁止自动重定向以便抓取 Location
            )
            
            # 判定跳转结果
            if api_resp.status_code == 302:
                location = api_resp.headers.get('Location', '')
                if 'renew=success' in location:
                    log('🎉 自动续订成功！')
                    send_telegram(f'✅ <b>KataBump 续订成功</b>\n服务器: <code>{SERVER_ID}</code>\n新日期: {expiry}(已刷新)')
                elif 'error=captcha' in location:
                    log('❌ 触发验证码')
                    send_telegram(f'⚠️ <b>需要手动验证</b>\n服务器: {SERVER_ID}\n原因: 触发了人机验证，请手动登录操作。')
                else:
                    log(f'ℹ️ 接口反馈: {location.split("/")[-1]}')
            else:
                log(f'📥 响应码 {api_resp.status_code}，目前可能无需续订。')

    except Exception as e:
        log(f'❌ 错误: {e}')
        send_telegram(f'❌ <b>KataBump 脚本报错</b>\n服务器: {SERVER_ID}\n错误: {e}')

def main():
    # 满足你的需求：启动就发通知
    send_telegram("🚀 <b>KataBump 保活脚本开始工作</b>")
    log('=' * 50)
    if not KATA_EMAIL or not KATA_PASSWORD:
        log('❌ 缺失 KATA_EMAIL 或 KATA_PASSWORD')
        return
    run()
    log('🏁 任务完成')

if __name__ == '__main__':
    main()

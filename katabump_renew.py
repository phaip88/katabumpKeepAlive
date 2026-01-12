#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import re
import requests
from datetime import datetime, timezone, timedelta

# ================= 配置区 =================
DASHBOARD_URL = 'https://dashboard.katabump.com'
# 请确保 GitHub Secret 中的 KATA_SERVER_ID 是 201692
SERVER_ID = os.environ.get('KATA_SERVER_ID', '201692')
KATA_EMAIL = os.environ.get('KATA_EMAIL', '')
KATA_PASSWORD = os.environ.get('KATA_PASSWORD', '')
TG_BOT_TOKEN = os.environ.get('TG_BOT_TOKEN', '')
TG_CHAT_ID = os.environ.get('TG_USER_ID', '') 

def log(msg):
    tz = timezone(timedelta(hours=8))
    t = datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S')
    print(f'[{t}] {msg}')

def send_telegram(message):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        return False
    try:
        requests.post(
            f'https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage',
            json={'chat_id': TG_CHAT_ID, 'text': message, 'parse_mode': 'HTML'},
            timeout=30
        )
        return True
    except:
        return False

def get_expiry(html):
    # 针对 Dashboard 页面优化的正则
    patterns = [
        r'Expiry[\s\S]{0,100}?>\s*(\d{4}-\d{2}-\d{2})',
        r'(\d{4}-\d{2}-\d{2})'
    ]
    for p in patterns:
        match = re.search(p, html, re.IGNORECASE)
        if match: return match.group(1)
    return None

def get_csrf(html):
    # 抓取续订所需的 CSRF
    m = re.search(r'name=["\']csrf["\'][^>]*value=["\']([^"\']+)["\']', html)
    return m.group(1) if m else None

def run():
    log(f'🚀 开始保活检查 - 目标 ID: {SERVER_ID}')
    session = requests.Session()
    # 使用你原本成功的浏览器头
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    })
    
    try:
        # 1. 登录 (回归最简成功逻辑)
        log('🔐 正在登录 Dashboard...')
        session.get(f'{DASHBOARD_URL}/auth/login', timeout=30)
        login_resp = session.post(
            f'{DASHBOARD_URL}/auth/login',
            data={'email': KATA_EMAIL, 'password': KATA_PASSWORD, 'remember': 'true'},
            headers={'Referer': f'{DASHBOARD_URL}/auth/login'},
            timeout=30,
            allow_redirects=True
        )
        
        if '/auth/login' in login_resp.url:
            raise Exception("登录失败：页面未跳转，请检查 Secrets 中的邮箱和密码是否有误或包含多余空格。")
        log('✅ 登录成功')
        
        # 2. 获取续订页面信息
        target_page = f'{DASHBOARD_URL}/servers/edit?id={SERVER_ID}'
        log(f'🔎 正在读取管理页: {target_page}')
        server_page = session.get(target_page, timeout=30)
        
        expiry = get_expiry(server_page.text)
        csrf_token = get_csrf(server_page.text)
        log(f'📅 到期日期: {expiry or "未知"}')

        # 3. 尝试续订动作
        # 逻辑：无论日期是否抓到，都尝试 POST
        log('🔄 正在尝试发送续订请求...')
        api_resp = session.post(
            f'{DASHBOARD_URL}/api-client/renew?id={SERVER_ID}',
            data={'csrf': csrf_token} if csrf_token else {},
            headers={'Referer': target_page},
            timeout=30, 
            allow_redirects=False # 捕捉 302 跳转
        )
        
        location = api_resp.headers.get('Location', '')
        
        if 'renew=success' in location:
            send_telegram(f'✅ <b>KataBump 续订成功</b>\nID: {SERVER_ID}\n新到期日: {expiry or "已刷新"}')
            log('🎉 续订成功！')
        elif 'error=captcha' in location:
            send_telegram(f'⚠️ <b>续订失败：需要验证码</b>\nID: {SERVER_ID}\n请手动点击一次续订。')
            log('❌ 需要验证码')
        elif api_resp.status_code == 400:
            log('⏳ 尚未到续订时间 (API 返回 400)')
            # 只有在抓不到日期的情况下才发“平安报”，抓到了日期就不骚扰了
            if not expiry:
                send_telegram(f'ℹ️ <b>KataBump 状态正常</b>\nID: {SERVER_ID}\n状态: 无需续订\n注: 日期抓取仍有偏差。')
        else:
            log(f'📥 接口响应码: {api_resp.status_code}，未触发跳转。')

    except Exception as e:
        log(f'❌ 运行报错: {e}')
        send_telegram(f'❌ <b>KataBump 脚本报错</b>\n目标ID: {SERVER_ID}\n详情: {e}')

def main():
    # 启动通知：用于确认脚本确实在 GitHub Actions 上跑起来了
    send_telegram(f'🕒 <b>KataBump 检查启动</b>\n目标ID: {SERVER_ID}')
    run()

if __name__ == '__main__':
    main()

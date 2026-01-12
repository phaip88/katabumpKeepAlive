#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import re
import requests
from datetime import datetime, timezone, timedelta

# 配置
DASHBOARD_URL = 'https://dashboard.katabump.com'
# 建议在 GitHub Secrets 中设置，代码里保留一个默认值
SERVER_ID = os.environ.get('KATA_SERVER_ID', '201692')
KATA_EMAIL = os.environ.get('KATA_EMAIL', '')
KATA_PASSWORD = os.environ.get('KATA_PASSWORD', '')
TG_BOT_TOKEN = os.environ.get('TG_BOT_TOKEN', '')
TG_CHAT_ID = os.environ.get('TG_USER_ID', '') 

# 执行器名称
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
    # 增强版正则：依次尝试 1.Expiry标签后 2.Input框value里 3.页面任何日期格式
    patterns = [
        r'Expiry[\s\S]*?>\s*(\d{4}-\d{2}-\d{2})',
        r'value=["\'](\d{4}-\d{2}-\d{2})["\']',
        r'(\d{4}-\d{2}-\d{2})'
    ]
    for p in patterns:
        match = re.search(p, html, re.IGNORECASE)
        if match: return match.group(1)
    return None

def get_csrf(html):
    patterns = [
        r'name=["\']csrf["\'][^>]*value=["\']([^"\']+)["\']',
        r'value=["\']([^"\']+)["\'][^>]*name=["\']csrf["\']',
    ]
    for p in patterns:
        m = re.search(p, html, re.IGNORECASE)
        if m: return m.group(1)
    return None

def days_until(date_str):
    try:
        if not date_str: return None
        exp = datetime.strptime(date_str, '%Y-%m-%d')
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        return (exp - today).days
    except:
        return None

def run():
    log(f'🚀 开始执行 - 服务器 ID: {SERVER_ID}')
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    })
    
    try:
        # 1. 登录
        log('🔐 登录中...')
        session.get(f'{DASHBOARD_URL}/auth/login', timeout=30)
        login_resp = session.post(
            f'{DASHBOARD_URL}/auth/login',
            data={'email': KATA_EMAIL, 'password': KATA_PASSWORD, 'remember': 'true'},
            headers={'Content-Type': 'application/x-www-form-urlencoded', 'Referer': f'{DASHBOARD_URL}/auth/login'},
            timeout=30
        )
        if '/auth/login' in login_resp.url: raise Exception('登录失败，请检查账号密码')
        log('✅ 登录成功')
        
        # 2. 访问管理页
        server_page = session.get(f'{DASHBOARD_URL}/servers/edit?id={SERVER_ID}', timeout=30)
        expiry = get_expiry(server_page.text)
        days = days_until(expiry)
        csrf = get_csrf(server_page.text)
        log(f'📅 抓取到期日期: {expiry or "未知"} (剩余 {days if days is not None else "未知"} 天)')
        
        # 3. 尝试续订 (无论日期是否已知，只要没到期很远就点一下)
        if days is None or days <= 2:
            log('🔄 满足触发条件或日期未知，发送续订请求...')
            # 必须设置 allow_redirects=False 来捕捉 302 跳转
            api_resp = session.post(
                f'{DASHBOARD_URL}/api-client/renew?id={SERVER_ID}',
                data={'csrf': csrf} if csrf else {},
                headers={'Referer': f'{DASHBOARD_URL}/servers/edit?id={SERVER_ID}'},
                timeout=30,
                allow_redirects=False 
            )
            
            # 判定结果
            status = api_resp.status_code
            location = api_resp.headers.get('Location', '')
            log(f'📥 API 响应码: {status}, 跳转位置: {location}')
            
            if 'renew=success' in location:
                log('🎉 自动续订成功！')
                send_telegram(f'✅ <b>KataBump 续订成功</b>\n服务器: {SERVER_ID}\n新日期: {expiry or "已更新"}')
            elif 'error=captcha' in location:
                log('❌ 需要验证码')
                send_telegram(f'⚠️ <b>需要手动验证</b>\n服务器: {SERVER_ID}\n原因: 触发了人机验证。')
            elif status == 400:
                log('⏳ 接口返回 400 (可能未到续订时间)')
            else:
                log('ℹ️ 请求已发送，但未触发成功跳转。')
        else:
            log('😴 剩余天数充足，无需续订。')

    except Exception as e:
        log(f'❌ 错误: {e}')
        send_telegram(f'❌ <b>KataBump 脚本异常</b>\n错误: {e}')

def main():
    # 启动时简单打个招呼，确认脚本在跑
    log('=' * 50)
    if not KATA_EMAIL or not KATA_PASSWORD:
        log('❌ 缺少账号密码环境变量')
        return
    run()
    log('🏁 任务完成')

if __name__ == '__main__':
    main()

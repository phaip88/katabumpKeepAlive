#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KataBump 自动续订/提醒脚本 (GitHub Actions 优化版)
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
TG_CHAT_ID = os.environ.get('TG_USER_ID', '')
EXECUTOR_NAME = os.environ.get('EXECUTOR_NAME', 'GitHub Actions')

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
        log('✅ Telegram 通知已发送')
        return True
    except Exception as e:
        log(f'❌ Telegram 错误: {e}')
    return False

def get_expiry(html):
    # 增强版正则：兼容更多状态下的日期抓取
    patterns = [
        r'Expiry[\s\S]*?(\d{4}-\d{2}-\d{2})', # 标准日期
        r'(\d{4}-\d{2}-\d{2})',              # 任意位置的日期格式
        r'expires in (\d+) days'             # 相对时间
    ]
    for p in patterns:
        match = re.search(p, html, re.IGNORECASE)
        if match:
            return match.group(1)
    return None

def days_until(date_str):
    try:
        if not date_str: return None
        if date_str.isdigit(): return int(date_str) # 处理 "expires in X days"
        exp = datetime.strptime(date_str, '%Y-%m-%d')
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        return (exp - today).days
    except:
        return None

def parse_renew_error(url):
    if 'renew-error' not in url:
        return None, None
    error_match = re.search(r'renew-error=([^&]+)', url)
    if not error_match:
        return '未知错误', None
    error = requests.utils.unquote(error_match.group(1).replace('+', ' '))
    return error, None

def run():
    log(f'🚀 开始执行 - 服务器 ID: {SERVER_ID}')
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    })
    
    try:
        # 1. 登录
        session.get(f'{DASHBOARD_URL}/auth/login', timeout=30)
        login_resp = session.post(
            f'{DASHBOARD_URL}/auth/login',
            data={'email': KATA_EMAIL, 'password': KATA_PASSWORD, 'remember': 'true'},
            timeout=30,
            allow_redirects=True
        )
        
        if '/auth/login' in login_resp.url:
            raise Exception('登录失败，请检查账号密码')
        log('✅ 登录成功')
        
        # 2. 获取信息
        server_page = session.get(f'{DASHBOARD_URL}/servers/edit?id={SERVER_ID}', timeout=30)
        expiry = get_expiry(server_page.text)
        days = days_until(expiry)
        csrf = get_csrf_content(server_page.text)
        
        log(f'📅 到期: {expiry or "未知"} (剩余 {days if days is not None else "未知"} 天)')
        
        # 3. 尝试续订 (只要剩余小于3天或抓取不到日期，就尝试)
        if days is None or days <= 2:
            log('🔄 满足条件，尝试续订请求...')
            api_url = f'{DASHBOARD_URL}/api-client/renew?id={SERVER_ID}'
            api_resp = session.post(
                api_url,
                data={'csrf': csrf} if csrf else {},
                headers={'Referer': f'{DASHBOARD_URL}/servers/edit?id={SERVER_ID}'},
                timeout=30,
                allow_redirects=False
            )
            
            # 处理结果
            if api_resp.status_code == 302:
                location = api_resp.headers.get('Location', '')
                if 'renew=success' in location:
                    send_telegram(f'🎉 续订成功！服务器: {SERVER_ID}\n新日期: {expiry}')
                elif 'error=captcha' in location:
                    send_telegram(f'⚠️ 需要验证码！自动续订失败，请手动处理 ID: {SERVER_ID}')
                elif 'renew-error' in location:
                    err, _ = parse_renew_error(location)
                    log(f'⏳ 暂不可续订: {err}')
                    # 只有在真的快过期时才发预警
                    if days is not None and days <= 1:
                        send_telegram(f'ℹ️ 续订预警\nID: {SERVER_ID}\n剩余: {days}天\n状态: {err}')
            else:
                log(f'📥 响应码: {api_resp.status_code}，目前无需续订或接口变动')

    except Exception as e:
        log(f'❌ 错误: {e}')
        send_telegram(f'❌ 脚本执行异常\nID: {SERVER_ID}\n错误: {e}')

def get_csrf_content(html):
    m = re.search(r'name=["\']csrf["\'][^>]*value=["\']([^"\']+)["\']', html)
    return m.group(1) if m else None

def main():
    if not KATA_EMAIL or not KATA_PASSWORD:
        log('❌ 缺失环境变量')
        return
    run()
    log('🏁 完成')

if __name__ == '__main__':
    main()

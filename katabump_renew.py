#!/usr/bin/env python3
# -*- coding: utf-8 -*-

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
    # 终极版正则：兼容各种可能的 HTML 结构和空格
    patterns = [
        r'Expiry[\s\S]{0,100}?>\s*(\d{4}-\d{2}-\d{2})', # 找 Expiry 标签后的日期
        r'value=["\'](\d{4}-\d{2}-\d{2})',              # 找 input 的 value
        r'(\d{4}-\d{2}-\d{2})'                         # 页面中任何 202x-xx-xx 格式
    ]
    for p in patterns:
        match = re.search(p, html, re.IGNORECASE)
        if match: return match.group(1)
    return None

def run():
    log(f'🚀 正在检查服务器: {SERVER_ID}')
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
            timeout=30
        )
        if '/auth/login' in login_resp.url: raise Exception('登录失败，账号密码可能错误')
        
        # 2. 抓取信息
        server_page = session.get(f'{DASHBOARD_URL}/servers/edit?id={SERVER_ID}', timeout=30)
        expiry = get_expiry(server_page.text)
        csrf = re.search(r'name=["\']csrf["\'][^>]*value=["\']([^"\']+)["\']', server_page.text)
        csrf_token = csrf.group(1) if csrf else ""
        
        log(f'📅 到期日期: {expiry or "未知"}')

        # 3. 尝试续订
        api_resp = session.post(
            f'{DASHBOARD_URL}/api-client/renew?id={SERVER_ID}',
            data={'csrf': csrf_token},
            headers={'Referer': f'{DASHBOARD_URL}/servers/edit?id={SERVER_ID}'},
            timeout=30, allow_redirects=False
        )
        
        location = api_resp.headers.get('Location', '')
        
        if 'renew=success' in location:
            send_telegram(f'✅ <b>KataBump 续订成功</b>\nID: {SERVER_ID}\n到期: {expiry or "已刷新"}')
        elif 'error=captcha' in location:
            send_telegram(f'⚠️ <b>需要手动验证码</b>\nID: {SERVER_ID}')
        elif api_resp.status_code == 400:
            log('⏳ 尚未到续订时间 (400)')
            # 如果日期抓取失败且遇到 400，也发个状态报告
            if not expiry:
                send_telegram(f'ℹ️ <b>KataBump 运行报告</b>\nID: {SERVER_ID}\n状态: 正常(无需续订)\n注意: 日期抓取失败，请检查面板。')
        else:
            log('ℹ️ 未触发续订动作')

    except Exception as e:
        send_telegram(f'❌ <b>脚本执行报错</b>\n错误: {e}')

def main():
    # 强制先发一条“正在运行”的通知
    send_telegram(f'🕒 <b>KataBump 保活检查启动</b>\n服务器ID: {SERVER_ID}')
    run()

if __name__ == '__main__':
    main()

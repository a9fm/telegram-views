#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import aiohttp
import asyncio
from aiohttp_socks import ProxyConnector
import re
import random
import os
from datetime import datetime
from fake_useragent import UserAgent
import json

# ============================================
# 📋 НАСТРОЙКИ
# ============================================
WORKING_FILE = "working.txt"
DEAD_FILE = "dead.txt"
POSTS_COUNT = 3
VIEWS_PER_POST = 10
CONCURRENCY = 50  # Можно больше, т.к. не браузер
PROXY_TIMEOUT = 5

# ============================================
# 📊 СТАТИСТИКА
# ============================================
stats = {
    'tested': 0,
    'working': 0,
    'dead': 0,
    'views_sent': 0,
    'start_time': datetime.now()
}

# ============================================
# 🔧 ВСПОМОГАТЕЛЬНЫЕ
# ============================================
def log(message):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")

def update_progress():
    elapsed = (datetime.now() - stats['start_time']).total_seconds()
    speed = stats['tested'] / elapsed if elapsed > 0 else 0
    print(f"\r📊 Прогресс: ✅ {stats['working']} | 💀 {stats['dead']} | 👁️ {stats['views_sent']} | ⚡ {speed:.1f}/с | Время: {elapsed:.0f}с", end="", flush=True)

def load_working_proxies():
    if not os.path.exists(WORKING_FILE):
        return []
    with open(WORKING_FILE, "r") as f:
        return [line.strip() for line in f if line.strip()]

def save_working_proxy(proxy):
    with open(WORKING_FILE, "a") as f:
        f.write(proxy + "\n")
    stats['working'] += 1

# ============================================
# 🌐 ПАРСИНГ ПОСТОВ
# ============================================
async def get_last_posts(channel):
    """Получает последние посты канала"""
    url = f"https://t.me/s/{channel}"
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, timeout=10) as response:
                html = await response.text()
                
                # Ищем ID постов
                pattern = r'data-post="' + channel + r'/(\d+)"'
                post_ids = re.findall(pattern, html)
                
                if not post_ids:
                    pattern = r'href="/' + channel + r'/(\d+)"'
                    post_ids = re.findall(pattern, html)
                
                # Убираем дубликаты
                unique = list(dict.fromkeys(post_ids))
                last_3 = [int(id) for id in unique][-3:]
                
                log(f"📡 Найдено постов: {last_3}")
                return last_3
                
        except Exception as e:
            log(f"❌ Ошибка: {e}")
            return []

# ============================================
# 🎯 ОТПРАВКА ПРОСМОТРА
# ============================================
async def send_view(channel, post_id, proxy_url=None):
    """Отправляет просмотр через прямой запрос"""
    url = f"https://t.me/{channel}/{post_id}"
    
    try:
        connector = None
        if proxy_url:
            connector = ProxyConnector.from_url(proxy_url, rdns=True)
        
        async with aiohttp.ClientSession(connector=connector) as session:
            # 1. Получаем страницу с токеном
            headers = {
                "User-Agent": UserAgent().random,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
                "Connection": "keep-alive",
            }
            
            async with session.get(
                f"https://t.me/{channel}/{post_id}?embed=1&mode=tme",
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=PROXY_TIMEOUT)
            ) as resp:
                
                if resp.status != 200:
                    return False
                
                html = await resp.text()
                
                # Ищем токен
                token_match = re.search('data-view="([^"]+)"', html)
                if not token_match:
                    return False
                
                token = token_match.group(1)
                
                # 2. Отправляем просмотр
                view_headers = {
                    "User-Agent": headers["User-Agent"],
                    "Referer": f"https://t.me/{channel}/{post_id}?embed=1&mode=tme",
                    "X-Requested-With": "XMLHttpRequest",
                }
                
                async with session.post(
                    f"https://t.me/v/?views={token}",
                    headers=view_headers,
                    timeout=aiohttp.ClientTimeout(total=PROXY_TIMEOUT)
                ) as view_resp:
                    
                    if view_resp.status == 200:
                        text = await view_resp.text()
                        if text == "true":
                            stats['views_sent'] += 1
                            update_progress()
                            return True
        
        return False
        
    except Exception as e:
        return False

# ============================================
# 🚀 ЗАПУСК
# ============================================
async def main():
    print("="*50)
    print("🤖 Telegram View Bot (Pure HTTP)")
    print("="*50)
    
    # Ввод
    channel = input("📢 Канал (без @): ").strip() or "a9fm_price"
    
    # Посты
    post_ids = await get_last_posts(channel)
    if not post_ids:
        log("❌ Нет постов")
        return
    
    # Прокси
    proxies = load_working_proxies()
    if not proxies:
        log("❌ Нет прокси в working.txt")
        return
    
    log(f"✅ Загружено {len(proxies)} прокси")
    log(f"🎯 Посты: {post_ids}")
    log(f"🚀 Запуск {VIEWS_PER_POST} просмотров на пост...")
    
    # Создаем задачи
    tasks = []
    for post_id in post_ids:
        for _ in range(VIEWS_PER_POST):
            proxy = random.choice(proxies)
            tasks.append(send_view(channel, post_id, proxy))
    
    # Запускаем
    results = await asyncio.gather(*tasks)
    
    # Итог
    success = sum(1 for r in results if r)
    elapsed = (datetime.now() - stats['start_time']).total_seconds()
    
    print("\n" + "="*50)
    print("🏁 ГОТОВО")
    print(f"✅ Успешно: {success}/{len(tasks)}")
    print(f"👁️ Просмотров: {stats['views_sent']}")
    print(f"⏱️ Время: {elapsed:.1f}с")
    print("="*50)

if __name__ == "__main__":
    asyncio.run(main())

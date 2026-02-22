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

# ============================================
# 📋 НАСТРОЙКИ
# ============================================
WORKING_FILE = "working.txt"
DEAD_FILE = "dead.txt"
POSTS_COUNT = 3
VIEWS_PER_POST = 10
CONCURRENCY = 100
PROXY_TIMEOUT = 5

# Пути к файлам с источниками
AUTO_HTTP = "auto/http.txt"
AUTO_SOCKS4 = "auto/socks4.txt"
AUTO_SOCKS5 = "auto/socks5.txt"

# ============================================
# 📊 СТАТИСТИКА
# ============================================
stats = {
    'tested': 0,
    'working': 0,
    'dead': 0,
    'views_sent': 0,
    'parsed': 0,
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
    print(f"\r📊 Прогресс: ✅ {stats['working']} | 💀 {stats['dead']} | 👁️ {stats['views_sent']} | 📥 {stats['parsed']} | ⚡ {speed:.1f}/с | Время: {elapsed:.0f}с", end="", flush=True)

def load_working_proxies():
    if os.path.exists(WORKING_FILE):
        with open(WORKING_FILE, "r") as f:
            return [line.strip() for line in f if line.strip()]
    return []

def save_working_proxy(proxy):
    with open(WORKING_FILE, "a") as f:
        f.write(proxy + "\n")
    stats['working'] += 1

def save_dead_proxy(proxy):
    with open(DEAD_FILE, "a") as f:
        f.write(proxy + "\n")
    stats['dead'] += 1

# ============================================
# 📖 ЧТЕНИЕ ИСТОЧНИКОВ ИЗ ФАЙЛОВ
# ============================================
def load_source_urls():
    """Загружает ссылки на прокси из файлов auto/"""
    sources = {
        'http': [],
        'socks4': [],
        'socks5': []
    }
    
    # Читаем http.txt
    if os.path.exists(AUTO_HTTP):
        with open(AUTO_HTTP, 'r') as f:
            sources['http'] = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        log(f"📁 Загружено {len(sources['http'])} HTTP источников")
    
    # Читаем socks4.txt
    if os.path.exists(AUTO_SOCKS4):
        with open(AUTO_SOCKS4, 'r') as f:
            sources['socks4'] = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        log(f"📁 Загружено {len(sources['socks4'])} SOCKS4 источников")
    
    # Читаем socks5.txt
    if os.path.exists(AUTO_SOCKS5):
        with open(AUTO_SOCKS5, 'r') as f:
            sources['socks5'] = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        log(f"📁 Загружено {len(sources['socks5'])} SOCKS5 источников")
    
    return sources

# ============================================
# 🌐 ПАРСИНГ ПРОКСИ С ИСТОЧНИКОВ
# ============================================
async def parse_proxies_from_url(source_url: str, proxy_type: str):
    """Парсит прокси с URL источника"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(source_url, timeout=15) as resp:
                if resp.status == 200:
                    text = await resp.text()
                    # Ищем IP:port
                    pattern = r'\b(?:\d{1,3}\.){3}\d{1,3}:\d{2,5}\b'
                    proxies = re.findall(pattern, text)
                    
                    # Добавляем тип
                    result = [f"{proxy_type}://{p}" for p in proxies]
                    log(f"📥 {source_url.split('/')[-1]}: {len(result)} {proxy_type} прокси")
                    return result
    except Exception as e:
        log(f"❌ Ошибка загрузки {source_url}: {e}")
    return []

async def parse_all_proxies():
    """Парсит прокси со всех источников из auto/ файлов"""
    log("🔍 Начинаю парсинг прокси из источников...")
    
    sources = load_source_urls()
    all_proxies = []
    tasks = []
    
    for proxy_type, urls in sources.items():
        for url in urls:
            tasks.append(parse_proxies_from_url(url, proxy_type))
    
    if not tasks:
        log("❌ Нет источников для парсинга!")
        return []
    
    results = await asyncio.gather(*tasks)
    
    for proxies in results:
        all_proxies.extend(proxies)
    
    # Убираем дубликаты
    unique = list(set(all_proxies))
    stats['parsed'] = len(unique)
    
    log(f"📊 Всего спарсено: {len(all_proxies)} прокси, уникальных: {len(unique)}")
    return unique

# ============================================
# 🔍 ПРОВЕРКА ПРОКСИ
# ============================================
async def check_proxy(proxy_url: str, test_url: str):
    """Проверяет работает ли прокси"""
    try:
        connector = ProxyConnector.from_url(proxy_url, rdns=True)
        async with aiohttp.ClientSession(connector=connector) as session:
            headers = {"User-Agent": UserAgent().random}
            
            async with session.get(
                test_url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=PROXY_TIMEOUT)
            ) as response:
                
                if response.status == 200:
                    html = await response.text()
                    if 'data-view="' in html:
                        return True
        return False
    except:
        return False

async def test_proxies_batch(proxies, test_url):
    """Тестирует пачку прокси"""
    log(f"🧪 Тестирую {len(proxies)} прокси...")
    semaphore = asyncio.Semaphore(500)  
    
    async def test_one(proxy):
        async with semaphore:
            stats['tested'] += 1
            if await check_proxy(proxy, test_url):
                save_working_proxy(proxy)
                update_progress()
                return True
            else:
                save_dead_proxy(proxy)
                update_progress()
                return False
    
    tasks = [test_one(p) for p in proxies]
    results = await asyncio.gather(*tasks)
    
    working = [p for p, r in zip(proxies, results) if r]
    log(f"\n✅ Найдено {len(working)} рабочих прокси")
    return working

# ============================================
# 🎯 ОТПРАВКА ПРОСМОТРА
# ============================================
async def send_view(channel: str, post_id: int, proxy_url: str = None):
    """Отправляет просмотр"""
    try:
        connector = None
        if proxy_url:
            connector = ProxyConnector.from_url(proxy_url, rdns=True)
        
        async with aiohttp.ClientSession(connector=connector) as session:
            ua = UserAgent().random
            
            # Получаем токен
            headers = {
                "User-Agent": ua,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
            }
            
            embed_url = f"https://t.me/{channel}/{post_id}?embed=1&mode=tme"
            
            async with session.get(embed_url, headers=headers, timeout=PROXY_TIMEOUT) as resp:
                if resp.status != 200:
                    return False
                
                html = await resp.text()
                token_match = re.search(r'data-view="([^"]+)"', html)
                if not token_match:
                    return False
                
                token = token_match.group(1)
                
                # Отправляем просмотр
                view_headers = {
                    "User-Agent": ua,
                    "Referer": embed_url,
                    "X-Requested-With": "XMLHttpRequest",
                }
                
                async with session.post(
                    f"https://t.me/v/?views={token}",
                    headers=view_headers,
                    timeout=PROXY_TIMEOUT
                ) as view_resp:
                    
                    if view_resp.status == 200:
                        text = await view_resp.text()
                        if text == "true":
                            stats['views_sent'] += 1
                            update_progress()
                            return True
        return False
    except:
        return False

# ============================================
# 🌐 ПАРСИНГ ПОСТОВ
# ============================================
async def get_last_posts(channel: str):
    """Получает последние посты"""
    url = f"https://t.me/s/{channel}"
    
    async with aiohttp.ClientSession() as session:
        try:
            headers = {"User-Agent": UserAgent().random}
            async with session.get(url, headers=headers, timeout=10) as resp:
                html = await resp.text()
                
                # Ищем ID постов
                pattern = rf'data-post="{channel}/(\d+)"'
                post_ids = re.findall(pattern, html)
                
                if not post_ids:
                    pattern = rf'href="/{channel}/(\d+)"'
                    post_ids = re.findall(pattern, html)
                
                if post_ids:
                    unique = sorted(set(int(id) for id in post_ids))
                    last = unique[-POSTS_COUNT:]
                    log(f"📡 Найдено постов: {last}")
                    return last
        except Exception as e:
            log(f"❌ Ошибка: {e}")
    return []

# ============================================
# 🚀 РЕЖИМЫ РАБОТЫ
# ============================================
async def auto_mode(channel: str):
    """Режим AUTO - парсит прокси из auto/ файлов, тестирует, использует"""
    log("🚀 Запущен AUTO режим (с парсингом из auto/ файлов)")
    
    # 1. Получаем посты
    post_ids = await get_last_posts(channel)
    if not post_ids:
        log("❌ Нет постов")
        return
    
    # 2. Парсим свежие прокси из источников
    fresh_proxies = await parse_all_proxies()
    if not fresh_proxies:
        log("❌ Не удалось спарсить прокси")
        return
    
    # 3. Тестируем на первом посте
    test_url = f"https://t.me/{channel}/{post_ids[0]}?embed=1&mode=tme"
    working = await test_proxies_batch(fresh_proxies, test_url)
    
    if not working:
        log("❌ Нет рабочих прокси")
        return
    
    # 4. Запускаем накрутку
    log(f"🎯 Запуск накрутки на {post_ids}")
    all_tasks = []
    for post_id in post_ids:
        for _ in range(VIEWS_PER_POST):
            proxy = random.choice(working)
            all_tasks.append(send_view(channel, post_id, proxy))
    
    semaphore = asyncio.Semaphore(CONCURRENCY)
    
    async def run_with_limit(task):
        async with semaphore:
            return await task
    
    tasks = [run_with_limit(t) for t in all_tasks]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    success = sum(1 for r in results if r is True)
    log(f"\n✅ Накрутка: {success}/{len(all_tasks)} успешно")

async def list_mode(channel: str):
    """Режим LIST - использует готовые прокси из working.txt"""
    log("🚀 Запущен LIST режим")
    
    post_ids = await get_last_posts(channel)
    if not post_ids:
        log("❌ Нет постов")
        return
    
    proxies = load_working_proxies()
    if not proxies:
        log("❌ Нет прокси в working.txt")
        return
    
    log(f"✅ Использую {len(proxies)} готовых прокси")
    log(f"🎯 Посты: {post_ids}")
    
    all_tasks = []
    for post_id in post_ids:
        for _ in range(VIEWS_PER_POST):
            proxy = random.choice(proxies)
            all_tasks.append(send_view(channel, post_id, proxy))
    
    semaphore = asyncio.Semaphore(CONCURRENCY)
    
    async def run_with_limit(task):
        async with semaphore:
            return await task
    
    tasks = [run_with_limit(t) for t in all_tasks]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    success = sum(1 for r in results if r is True)
    log(f"\n✅ Накрутка: {success}/{len(all_tasks)} успешно")

# ============================================
# 📌 ТОЧКА ВХОДА
# ============================================
if __name__ == "__main__":
    import sys
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--channel", help="Канал без @")
    parser.add_argument("-m", "--mode", help="auto или list")
    args = parser.parse_args()
    
    if not args.channel:
        args.channel = input("📢 Канал (без @): ").strip()
    
    if not args.mode:
        print("\n1. Auto режим (парсинг из auto/ + тест + накрутка)")
        print("2. List режим (только накрутка из working.txt)")
        choice = input("\nВыбери (1/2): ").strip()
        args.mode = "auto" if choice == "1" else "list"
    
    print("=" * 50)
    print(f"🤖 Telegram Views Bot - {args.mode.upper()} режим")
    print("=" * 50)
    
    stats['start_time'] = datetime.now()
    
    if args.mode == "auto":
        asyncio.run(auto_mode(args.channel))
    else:
        asyncio.run(list_mode(args.channel))
    
    elapsed = (datetime.now() - stats['start_time']).total_seconds()
    print("\n" + "=" * 50)
    print("🏁 ГОТОВО")
    print(f"✅ Рабочих прокси: {stats['working']}")
    print(f"💀 Мертвых прокси: {stats['dead']}")
    print(f"👁️ Просмотров: {stats['views_sent']}")
    print(f"📥 Спарсено: {stats['parsed']}")
    print(f"⏱️ Время: {elapsed:.1f}с")
    print("=" * 50)

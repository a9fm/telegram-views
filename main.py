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
CONCURRENCY = 100
PROXY_TIMEOUT = 5
MAX_USES_PER_PROXY = 5  # Каждый прокси можно использовать 5 раз

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

def load_dead_proxies():
    if os.path.exists(DEAD_FILE):
        with open(DEAD_FILE, "r") as f:
            return set(line.strip() for line in f if line.strip())
    return set()

# ============================================
# 📖 ЧТЕНИЕ ИСТОЧНИКОВ ИЗ ФАЙЛОВ
# ============================================
def load_source_urls():
    sources = {'http': [], 'socks4': [], 'socks5': []}
    
    if os.path.exists(AUTO_HTTP):
        with open(AUTO_HTTP, 'r') as f:
            sources['http'] = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        log(f"📁 Загружено {len(sources['http'])} HTTP источников")
    
    if os.path.exists(AUTO_SOCKS4):
        with open(AUTO_SOCKS4, 'r') as f:
            sources['socks4'] = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        log(f"📁 Загружено {len(sources['socks4'])} SOCKS4 источников")
    
    if os.path.exists(AUTO_SOCKS5):
        with open(AUTO_SOCKS5, 'r') as f:
            sources['socks5'] = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        log(f"📁 Загружено {len(sources['socks5'])} SOCKS5 источников")
    
    return sources

# ============================================
# 🌐 ПАРСИНГ ПРОКСИ С ИСТОЧНИКОВ
# ============================================
async def parse_proxies_from_url(source_url: str, proxy_type: str):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(source_url, timeout=15) as resp:
                if resp.status == 200:
                    text = await resp.text()
                    pattern = r'\b(?:\d{1,3}\.){3}\d{1,3}:\d{2,5}\b'
                    proxies = re.findall(pattern, text)
                    result = [f"{proxy_type}://{p}" for p in proxies]
                    log(f"📥 {source_url.split('/')[-1]}: {len(result)} {proxy_type} прокси")
                    return result
    except:
        pass
    return []

async def parse_all_proxies():
    log("🔍 Начинаю парсинг прокси из источников...")
    
    sources = load_source_urls()
    all_proxies = []
    tasks = []
    
    for proxy_type, urls in sources.items():
        for url in urls:
            tasks.append(parse_proxies_from_url(url, proxy_type))
    
    results = await asyncio.gather(*tasks)
    
    for proxies in results:
        all_proxies.extend(proxies)
    
    unique = list(set(all_proxies))
    stats['parsed'] = len(unique)
    
    dead_set = load_dead_proxies()
    alive = [p for p in unique if p not in dead_set]
    
    log(f"📊 Всего: {len(all_proxies)} → уникальных: {len(unique)} → без мертвых: {len(alive)}")
    return alive

# ============================================
# 🔍 ПРОВЕРКА ПРОКСИ
# ============================================
async def check_proxy(proxy_url: str, test_url: str):
    try:
        connector = ProxyConnector.from_url(proxy_url, rdns=True)
        async with aiohttp.ClientSession(connector=connector) as session:
            headers = {"User-Agent": UserAgent().random}
            async with session.get(test_url, headers=headers, timeout=aiohttp.ClientTimeout(total=PROXY_TIMEOUT)) as response:
                if response.status == 200:
                    html = await response.text()
                    if 'data-view="' in html:
                        return True
    except:
        pass
    return False

async def test_proxies_batch(proxies, test_url):
    log(f"🧪 Тестирую {len(proxies)} прокси...")
    
    dead_set = load_dead_proxies()
    proxies = [p for p in proxies if p not in dead_set]
    log(f"📉 После фильтрации мертвых: {len(proxies)}")
    
    semaphore = asyncio.Semaphore(200)
    working = []
    
    async def test_one(proxy):
        async with semaphore:
            stats['tested'] += 1
            if await check_proxy(proxy, test_url):
                save_working_proxy(proxy)
                working.append(proxy)
                update_progress()
                return True
            else:
                save_dead_proxy(proxy)
                update_progress()
                return False
    
    chunk_size = 1000
    for i in range(0, len(proxies), chunk_size):
        chunk = proxies[i:i+chunk_size]
        tasks = [test_one(p) for p in chunk]
        await asyncio.gather(*tasks)
        log(f"📊 Чанк {i//chunk_size + 1}: найдено {len(working)} рабочих")
        await asyncio.sleep(1)
    
    log(f"\n✅ Найдено {len(working)} рабочих прокси")
    return working

# ============================================
# 🎯 ОТПРАВКА ПРОСМОТРА
# ============================================
async def send_view(channel: str, post_id: int, proxy_url: str = None):
    try:
        connector = None
        if proxy_url:
            connector = ProxyConnector.from_url(proxy_url, rdns=True)
        
        async with aiohttp.ClientSession(connector=connector) as session:
            ua = UserAgent().random
            
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
    url = f"https://t.me/s/{channel}"
    
    async with aiohttp.ClientSession() as session:
        try:
            headers = {"User-Agent": UserAgent().random}
            async with session.get(url, headers=headers, timeout=10) as resp:
                html = await resp.text()
                
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
# 🚀 РЕЖИМ LIST (БЕСКОНЕЧНАЯ НАКРУТКА)
# ============================================
async def list_mode(channel: str):
    """Режим LIST - бесконечная накрутка, 5 попыток на прокси"""
    log("🚀 Запущен LIST режим (бесконечная накрутка)")
    
    post_ids = await get_last_posts(channel)
    if not post_ids:
        log("❌ Нет постов")
        return
    
    proxies = load_working_proxies()
    if not proxies:
        log("❌ Нет прокси в working.txt")
        return
    
    log(f"✅ Загружено {len(proxies)} прокси")
    log(f"🎯 Посты: {post_ids}")
    log(f"🔄 Каждый прокси будет использован максимум {MAX_USES_PER_PROXY} раз")
    
    # Словарь для отслеживания использованных прокси
    proxy_usage = {proxy: 0 for proxy in proxies}
    total_attempts = 0
    successful_views = 0
    
    try:
        while True:
            # Выбираем прокси которые использовались меньше MAX_USES_PER_PROXY раз
            available_proxies = [p for p in proxies if proxy_usage[p] < MAX_USES_PER_PROXY]
            
            if not available_proxies:
                log(f"❌ Все прокси использованы {MAX_USES_PER_PROXY} раз. Завершаю работу.")
                break
            
            # Создаем задачи для всех постов
            tasks = []
            for post_id in post_ids:
                proxy = random.choice(available_proxies)
                proxy_usage[proxy] += 1
                total_attempts += 1
                tasks.append(send_view(channel, post_id, proxy))
            
            # Запускаем параллельно
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Считаем успехи
            success = sum(1 for r in results if r is True)
            successful_views += success
            
            # Логируем прогресс
            success_rate = (successful_views / total_attempts * 100) if total_attempts > 0 else 0
            log(f"👁️ Успешно: {successful_views} | Попыток: {total_attempts} | {success_rate:.1f}% | Осталось прокси: {len(available_proxies)}")
            
            # Небольшая пауза между циклами
            await asyncio.sleep(0.5)
            
    except KeyboardInterrupt:
        log("\n🛑 Остановлено пользователем")
    
    # Итог
    elapsed = (datetime.now() - stats['start_time']).total_seconds()
    success_rate = (successful_views / total_attempts * 100) if total_attempts > 0 else 0
    
    log(f"\n📊 ИТОГ:")
    log(f"✅ Всего просмотров: {successful_views}")
    log(f"🔄 Всего попыток: {total_attempts}")
    log(f"📈 Процент успеха: {success_rate:.1f}%")
    log(f"⏱️ Время работы: {elapsed:.1f}с")

# ============================================
# 🚀 РЕЖИМ AUTO
# ============================================
async def auto_mode(channel: str):
    log("🚀 Запущен AUTO режим")
    
    post_ids = await get_last_posts(channel)
    if not post_ids:
        log("❌ Нет постов")
        return
    
    fresh_proxies = await parse_all_proxies()
    if not fresh_proxies:
        log("❌ Не удалось спарсить прокси")
        return
    
    test_url = f"https://t.me/{channel}/{post_ids[0]}?embed=1&mode=tme"
    working = await test_proxies_batch(fresh_proxies, test_url)
    
    if not working:
        log("❌ Нет рабочих прокси")
        return
    
    # После тестирования запускаем list_mode с новыми прокси
    global proxies
    proxies = working
    await list_mode(channel)

# ============================================
# 📌 ТОЧКА ВХОДА
# ============================================
if __name__ == "__main__":
    import sys
    
    channel = input("📢 Канал (без @): ").strip()
    
    print("\n1. Auto режим (парсинг из auto/ + тест + накрутка)")
    print("2. List режим (только накрутка из working.txt)")
    choice = input("\nВыбери (1/2): ").strip()
    
    print("=" * 50)
    mode = "AUTO" if choice == "1" else "LIST"
    print(f"🤖 Telegram Views Bot - {mode} режим")
    print("=" * 50)
    
    stats['start_time'] = datetime.now()
    
    if choice == "1":
        asyncio.run(auto_mode(channel))
    else:
        asyncio.run(list_mode(channel))

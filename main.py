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
CONCURRENCY = 300
PROXY_TIMEOUT = 10
MAX_USES_PER_PROXY = 5

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
            async with session.get(source_url, timeout=30) as resp:
                if resp.status == 200:
                    text = await resp.text()
                    pattern = r'\b(?:\d{1,3}\.){3}\d{1,3}:\d{2,5}\b'
                    proxies = re.findall(pattern, text)
                    result = [f"{proxy_type}://{p}" for p in proxies]
                    source_name = source_url.split('/')[-1] or source_url.split('/')[-2]
                    log(f"📥 {source_name}: {len(result)} {proxy_type} прокси")
                    return result
    except Exception as e:
        log(f"❌ Ошибка загрузки {source_url}: {str(e)[:50]}")
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
            headers = {
                "User-Agent": UserAgent().random,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
            }
            async with session.get(
                test_url, 
                headers=headers, 
                timeout=aiohttp.ClientTimeout(total=PROXY_TIMEOUT)
            ) as response:
                if response.status == 200:
                    html = await response.text()
                    if 'tgme_' in html or 'data-view=' in html or 'telegram' in html.lower():
                        return True
    except:
        pass
    return False

async def test_proxies_batch(proxies, test_url):
    log(f"🧪 Тестирую {len(proxies)} прокси...")
    
    dead_set = load_dead_proxies()
    proxies = [p for p in proxies if p not in dead_set]
    log(f"📉 После фильтрации мертвых: {len(proxies)}")
    
    semaphore = asyncio.Semaphore(300)
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
    
    chunk_size = 2000
    for i in range(0, len(proxies), chunk_size):
        chunk = proxies[i:i+chunk_size]
        tasks = [test_one(p) for p in chunk]
        await asyncio.gather(*tasks)
        log(f"📊 Чанк {i//chunk_size + 1}: найдено {len(working)} рабочих")
        await asyncio.sleep(0.5)
    
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
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            }
            
            embed_url = f"https://t.me/{channel}/{post_id}?embed=1&mode=tme"
            
            async with session.get(embed_url, headers=headers, timeout=PROXY_TIMEOUT) as resp:
                if resp.status != 200:
                    return False
                
                html = await resp.text()
                
                token_match = re.search(r'data-view="([^"]+)"', html)
                if not token_match:
                    token_match = re.search(r'data-view=\'([^\']+)\'', html)
                if not token_match:
                    token_match = re.search(r'data-view=([^>\s]+)', html)
                
                if not token_match:
                    return False
                
                token = token_match.group(1).strip('"').strip("'")
                
                view_headers = {
                    "User-Agent": ua,
                    "Referer": embed_url,
                    "X-Requested-With": "XMLHttpRequest",
                    "Accept": "*/*",
                    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
                }
                
                async with session.post(
                    f"https://t.me/v/?views={token}",
                    headers=view_headers,
                    timeout=PROXY_TIMEOUT
                ) as view_resp:
                    
                    if view_resp.status == 200:
                        text = await view_resp.text()
                        if text == "true" or "true" in text:
                            stats['views_sent'] += 1
                            update_progress()
                            if proxy_url:
                                with open("gold_proxies.txt", "a") as f:
                                    f.write(proxy_url + "\n")
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
            async with session.get(url, headers=headers, timeout=15) as resp:
                if resp.status != 200:
                    log(f"❌ Ошибка загрузки канала: {resp.status}")
                    return []
                
                html = await resp.text()
                
                patterns = [
                    rf'data-post="{channel}/(\d+)"',
                    rf'href="/{channel}/(\d+)"',
                    rf'data-post="//t.me/{channel}/(\d+)"',
                    rf'tgme_widget_message[^>]*data-post="{channel}/(\d+)"',
                ]
                
                post_ids = []
                for pattern in patterns:
                    found = re.findall(pattern, html)
                    post_ids.extend(found)
                
                if not post_ids:
                    log("❌ Не удалось найти посты")
                    return []
                
                unique = sorted(set(int(id) for id in post_ids))
                last = unique[-POSTS_COUNT:] if len(unique) >= POSTS_COUNT else unique
                
                log(f"📡 Найдено постов: {last}")
                return last
                
        except Exception as e:
            log(f"❌ Ошибка парсинга: {e}")
            return []

# ============================================
# 🚀 РЕЖИМ LIST - КРУТИТ НА ВСЕ 3 ПОСТА ЦИКЛОМ!
# ============================================
async def list_mode(channel: str):
    log("🚀 Запущен LIST режим - кручу на ВСЕ 3 поста циклом!")
    
    # Получаем посты - ВСЕ 3 ШТУКИ
    post_ids = await get_last_posts(channel)
    if not post_ids:
        log("❌ Нет постов")
        return
    
    # Загружаем прокси
    proxies = load_working_proxies()
    if not proxies:
        log("❌ Нет прокси в working.txt")
        return
    
    log(f"✅ Загружено {len(proxies)} прокси")
    log(f"🎯 ПОСТЫ ДЛЯ НАКРУТКИ: {post_ids}")  # ЯВНО ПОКАЗЫВАЮ ВСЕ ПОСТЫ
    log(f"🔄 Каждый прокси можно использовать {MAX_USES_PER_PROXY} раз")
    
    # Словарь для отслеживания использованных прокси
    proxy_usage = {proxy: 0 for proxy in proxies}
    total_attempts = 0
    successful_views = 0
    
    # Статистика по постам
    post_stats = {post_id: {'attempts': 0, 'success': 0} for post_id in post_ids}
    
    # Загружаем золотые прокси если есть
    gold_proxies = []
    if os.path.exists("gold_proxies.txt"):
        with open("gold_proxies.txt", "r") as f:
            gold_proxies = [line.strip() for line in f if line.strip()]
        log(f"✨ Загружено {len(gold_proxies)} золотых прокси")
    
    try:
        cycle = 1
        while True:
            log(f"\n🔄 ЦИКЛ {cycle} - Накрутка на посты: {post_ids}")
            
            # Проходим по КАЖДОМУ ПОСТУ по очереди
            for post_id in post_ids:
                # Выбираем прокси
                if gold_proxies and random.random() > 0.5:
                    available_proxies = gold_proxies
                else:
                    available_proxies = [p for p in proxies if proxy_usage[p] < MAX_USES_PER_PROXY]
                
                if not available_proxies and not gold_proxies:
                    log(f"❌ Все прокси использованы {MAX_USES_PER_PROXY} раз")
                    break
                
                # Берем прокси
                proxy = random.choice(available_proxies) if available_proxies else random.choice(gold_proxies) if gold_proxies else None
                
                if proxy in proxy_usage:
                    proxy_usage[proxy] += 1
                
                total_attempts += 1
                post_stats[post_id]['attempts'] += 1
                
                # Отправляем просмотр
                result = await send_view(channel, post_id, proxy)
                
                if result:
                    successful_views += 1
                    post_stats[post_id]['success'] += 1
            
            # Статистика после каждого цикла
            elapsed = (datetime.now() - stats['start_time']).total_seconds()
            success_rate = (successful_views / total_attempts * 100) if total_attempts > 0 else 0
            
            log(f"📊 Статистика после цикла {cycle}:")
            log(f"   👁️ Всего просмотров: {successful_views}")
            log(f"   🎯 Посты:")
            for post_id in post_ids:
                post_success = post_stats[post_id]['success']
                post_attempts = post_stats[post_id]['attempts']
                post_rate = (post_success / post_attempts * 100) if post_attempts > 0 else 0
                log(f"      - пост {post_id}: {post_success}/{post_attempts} ({post_rate:.1f}%)")
            log(f"   📈 Общий процент: {success_rate:.1f}%")
            log(f"   ⏱️ Время: {elapsed:.0f}с")
            
            cycle += 1
            
            # Проверяем остались ли прокси
            available = [p for p in proxies if proxy_usage[p] < MAX_USES_PER_PROXY]
            if not available and not gold_proxies:
                log("❌ Все прокси использованы. Завершаю работу.")
                break
            
            # Небольшая пауза между циклами
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        log("\n🛑 Остановлено пользователем")
    
    # ИТОГОВАЯ СТАТИСТИКА ПО ВСЕМ ПОСТАМ
    elapsed = (datetime.now() - stats['start_time']).total_seconds()
    success_rate = (successful_views / total_attempts * 100) if total_attempts > 0 else 0
    
    log(f"\n{'='*60}")
    log(f"🏁 ИТОГОВАЯ СТАТИСТИКА")
    log(f"{'='*60}")
    log(f"📊 ОБЩЕЕ:")
    log(f"   ✅ Всего просмотров: {successful_views}")
    log(f"   🔄 Всего попыток: {total_attempts}")
    log(f"   📈 Процент успеха: {success_rate:.1f}%")
    log(f"   ⏱️ Время работы: {elapsed:.1f}с")
    log(f"\n🎯 ПОСТАМ:")
    for post_id in post_ids:
        post_success = post_stats[post_id]['success']
        post_attempts = post_stats[post_id]['attempts']
        post_rate = (post_success / post_attempts * 100) if post_attempts > 0 else 0
        log(f"   - пост {post_id}: {post_success} просмотров из {post_attempts} попыток ({post_rate:.1f}%)")
    log(f"\n✨ Золотых прокси: {len(gold_proxies)}")
    log(f"{'='*60}")

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
    
    log(f"✅ Найдено {len(working)} рабочих прокси, запускаю накрутку...")
    
    with open(WORKING_FILE, "w") as f:
        for proxy in working:
            f.write(proxy + "\n")
    
    await list_mode(channel)

# ============================================
# 📌 ТОЧКА ВХОДА
# ============================================
if __name__ == "__main__":
    import sys
    
    print("=" * 60)
    print("🤖 TELEGRAM VIEWS BOT - КРУТИТ НА ВСЕ 3 ПОСТА!")
    print("=" * 60)
    
    channel = input("📢 Канал (без @): ").strip()
    if not channel:
        channel = "a9fm_price"
        print(f"⚠️ Использую {channel}")
    
    print("\n1. Auto режим (парсинг из auto/ + тест + накрутка)")
    print("2. List режим (только накрутка из working.txt)")
    print("3. Тест прокси (только проверить и сохранить рабочие)")
    
    choice = input("\nВыбери (1/2/3): ").strip()
    
    print("=" * 60)
    stats['start_time'] = datetime.now()
    
    if choice == "1":
        print("🤖 AUTO РЕЖИМ")
        print("=" * 60)
        asyncio.run(auto_mode(channel))
    elif choice == "2":
        print("🤖 LIST РЕЖИМ - КРУЧУ ВСЕ 3 ПОСТА!")
        print("=" * 60)
        asyncio.run(list_mode(channel))
    elif choice == "3":
        print("🔍 ТЕСТ ПРОКСИ")
        print("=" * 60)
        post_ids = asyncio.run(get_last_posts(channel))
        if post_ids:
            test_url = f"https://t.me/{channel}/{post_ids[0]}?embed=1&mode=tme"
            fresh_proxies = asyncio.run(parse_all_proxies())
            if fresh_proxies:
                asyncio.run(test_proxies_batch(fresh_proxies, test_url))
    else:
        print("❌ Неверный выбор")

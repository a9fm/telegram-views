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
CONCURRENCY = 100
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
# 🔧 ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================
def log(message):
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {message}")

def update_progress():
    elapsed = (datetime.now() - stats['start_time']).total_seconds()
    speed = stats['tested'] / elapsed if elapsed > 0 else 0
    print(f"\r📊 Прогресс: ✅ {stats['working']} | 💀 {stats['dead']} | 👁️ {stats['views_sent']} | ⚡ {speed:.1f}/с | Время: {elapsed:.0f}с", end="", flush=True)

def load_working_proxies():
    """Загружает рабочие прокси из файла"""
    if not os.path.exists(WORKING_FILE):
        return []
    try:
        with open(WORKING_FILE, "r", encoding='utf-8', errors='ignore') as f:
            proxies = [line.strip() for line in f if line.strip()]
        log(f"📁 Загружено {len(proxies)} рабочих прокси из {WORKING_FILE}")
        return proxies
    except Exception as e:
        log(f"❌ Ошибка загрузки: {e}")
        return []

def save_working_proxy(proxy_str):
    """Сохраняет рабочий прокси"""
    try:
        with open(WORKING_FILE, "a", encoding='utf-8', errors='ignore') as f:
            f.write(proxy_str + "\n")
        stats['working'] += 1
        log(f"💾 Сохранен рабочий: {proxy_str}")
        update_progress()
    except Exception as e:
        log(f"❌ Ошибка сохранения: {e}")

def save_dead_proxy(proxy_str):
    """Сохраняет мертвый прокси"""
    try:
        with open(DEAD_FILE, "a", encoding='utf-8', errors='ignore') as f:
            f.write(proxy_str + "\n")
        stats['dead'] += 1
        update_progress()
    except Exception:
        pass

# ============================================
# 🔍 ПРОВЕРКА ПРОКСИ
# ============================================
async def check_proxy(proxy_url: str, test_url: str):
    """Проверяет работает ли прокси с Telegram"""
    try:
        connector = ProxyConnector.from_url(proxy_url, rdns=True)
        async with aiohttp.ClientSession(connector=connector) as session:
            headers = {
                "User-Agent": UserAgent().random,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
                "Connection": "keep-alive",
            }
            
            async with session.get(
                test_url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=PROXY_TIMEOUT)
            ) as response:
                
                if response.status == 200:
                    html = await response.text()
                    # Проверяем наличие токена просмотра
                    if 'data-view="' in html:
                        return True
        return False
    except Exception as e:
        return False

# ============================================
# 🎯 ОТПРАВКА ПРОСМОТРА
# ============================================
async def send_view(channel: str, post_id: int, proxy_url: str = None):
    """Отправляет просмотр через прокси"""
    try:
        connector = None
        if proxy_url:
            connector = ProxyConnector.from_url(proxy_url, rdns=True)
        
        async with aiohttp.ClientSession(connector=connector) as session:
            # Генерируем User-Agent
            ua = UserAgent().random
            
            # 1. Получаем страницу с токеном
            headers = {
                "User-Agent": ua,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Cache-Control": "max-age=0",
            }
            
            embed_url = f"https://t.me/{channel}/{post_id}?embed=1&mode=tme"
            
            async with session.get(
                embed_url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=PROXY_TIMEOUT)
            ) as resp:
                
                if resp.status != 200:
                    return False
                
                html = await resp.text()
                
                # Ищем токен просмотра
                token_match = re.search(r'data-view="([^"]+)"', html)
                if not token_match:
                    return False
                
                token = token_match.group(1)
                
                # Сохраняем куки
                cookies = resp.cookies
                
                # 2. Отправляем просмотр
                view_headers = {
                    "User-Agent": ua,
                    "Accept": "*/*",
                    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
                    "Accept-Encoding": "gzip, deflate, br",
                    "Referer": embed_url,
                    "X-Requested-With": "XMLHttpRequest",
                    "Connection": "keep-alive",
                    "Sec-Fetch-Dest": "empty",
                    "Sec-Fetch-Mode": "cors",
                    "Sec-Fetch-Site": "same-origin",
                }
                
                view_url = f"https://t.me/v/?views={token}"
                
                async with session.post(
                    view_url,
                    headers=view_headers,
                    cookies=cookies,
                    timeout=aiohttp.ClientTimeout(total=PROXY_TIMEOUT)
                ) as view_resp:
                    
                    if view_resp.status == 200:
                        text = await view_resp.text()
                        if text == "true":
                            stats['views_sent'] += 1
                            update_progress()
                            return True
                        else:
                            log(f"⚠️ Ответ: {text}")
        
        return False
        
    except Exception as e:
        return False

# ============================================
# 🌐 ПАРСИНГ ПОСТОВ КАНАЛА
# ============================================
async def get_last_posts(channel: str, count: int = POSTS_COUNT):
    """Получает последние посты канала"""
    url = f"https://t.me/s/{channel}"
    
    async with aiohttp.ClientSession() as session:
        try:
            headers = {"User-Agent": UserAgent().random}
            
            async with session.get(url, headers=headers, timeout=10) as response:
                html = await response.text()
                
                # Ищем ID постов в разных форматах
                patterns = [
                    rf'data-post="{channel}/(\d+)"',
                    rf'href="/{channel}/(\d+)"',
                    rf'data-post="//t.me/{channel}/(\d+)"',
                ]
                
                post_ids = []
                for pattern in patterns:
                    found = re.findall(pattern, html)
                    post_ids.extend(found)
                
                if not post_ids:
                    log("❌ Не удалось найти посты")
                    return []
                
                # Убираем дубликаты и сортируем
                unique_ids = sorted(set(int(id) for id in post_ids))
                
                # Берем последние count
                last_posts = unique_ids[-count:]
                
                log(f"📡 Найдено постов: {last_posts}")
                return last_posts
                
        except Exception as e:
            log(f"❌ Ошибка парсинга канала: {e}")
            return []

# ============================================
# 🚀 ЗАПУСК НАКРУТКИ
# ============================================
async def run_views(channel: str, post_ids: list, proxies: list):
    """Запускает накрутку на все посты"""
    
    # Создаем задачи для всех постов
    all_tasks = []
    for post_id in post_ids:
        for _ in range(VIEWS_PER_POST):
            proxy = random.choice(proxies) if proxies else None
            all_tasks.append(send_view(channel, post_id, proxy))
    
    log(f"🚀 Запуск {len(all_tasks)} просмотров...")
    
    # Ограничиваем параллельность
    semaphore = asyncio.Semaphore(CONCURRENCY)
    
    async def run_with_limit(task):
        async with semaphore:
            return await task
    
    limited_tasks = [run_with_limit(task) for task in all_tasks]
    
    # Запускаем
    results = await asyncio.gather(*limited_tasks, return_exceptions=True)
    
    # Считаем успехи
    success = sum(1 for r in results if r is True)
    
    return success, len(all_tasks)

# ============================================
# 🚀 ГЛАВНАЯ ФУНКЦИЯ
# ============================================
async def main():
    print("=" * 50)
    print("🤖 TELEGRAM VIEWS BOT - СТАРАЯ РАБОЧАЯ ВЕРСИЯ")
    print("=" * 50)
    
    # Ввод канала
    channel = input("📢 Введите канал (без @): ").strip()
    if not channel:
        channel = "a9fm_price"
        log(f"⚠️ Использую {channel}")
    
    # Получаем посты
    post_ids = await get_last_posts(channel, POSTS_COUNT)
    if not post_ids:
        log("❌ Не удалось получить посты")
        return
    
    # Загружаем прокси
    proxies = load_working_proxies()
    if not proxies:
        log("❌ Нет прокси в working.txt")
        return
    
    log(f"✅ Загружено {len(proxies)} прокси")
    log(f"🎯 Посты: {post_ids}")
    
    # Запускаем накрутку
    success, total = await run_views(channel, post_ids, proxies)
    
    # Итог
    elapsed = (datetime.now() - stats['start_time']).total_seconds()
    print("\n" + "=" * 50)
    print("🏁 РЕЗУЛЬТАТЫ")
    print(f"✅ Успешно: {success}/{total}")
    print(f"👁️ Просмотров засчитано: {stats['views_sent']}")
    print(f"📊 Рабочих прокси: {stats['working']}")
    print(f"💀 Мертвых прокси: {stats['dead']}")
    print(f"⏱️ Время: {elapsed:.1f}с")
    print("=" * 50)

# ============================================
# 🔥 ТЕСТ ПРОКСИ (ОТДЕЛЬНО)
# ============================================
async def test_proxies_mode():
    """Режим тестирования прокси"""
    print("=" * 50)
    print("🔍 ТЕСТИРОВАНИЕ ПРОКСИ")
    print("=" * 50)
    
    channel = input("📢 Канал для теста: ").strip() or "a9fm_price"
    post_id = input("📢 Пост для теста: ").strip() or "816"
    
    test_url = f"https://t.me/{channel}/{post_id}?embed=1&mode=tme"
    
    # Загружаем прокси из файла
    if not os.path.exists("proxies.txt"):
        log("❌ Нет файла proxies.txt")
        return
    
    with open("proxies.txt", "r") as f:
        proxies = [line.strip() for line in f if line.strip()]
    
    log(f"📁 Загружено {len(proxies)} прокси для теста")
    
    # Тестируем
    semaphore = asyncio.Semaphore(50)
    
    async def test_one(proxy):
        async with semaphore:
            stats['tested'] += 1
            if await check_proxy(proxy, test_url):
                save_working_proxy(proxy)
                return True
            else:
                save_dead_proxy(proxy)
                return False
    
    tasks = [test_one(p) for p in proxies[:500]]  # Тестируем первые 500
    results = await asyncio.gather(*tasks)
    
    log(f"\n✅ Тест завершен: {stats['working']} рабочих из {len(proxies[:500])}")

# ============================================
# 📌 ТОЧКА ВХОДА
# ============================================
if __name__ == "__main__":
    import sys
    
    print("\n1. Запустить накрутку")
    print("2. Протестировать прокси")
    print("3. Выйти")
    
    choice = input("\nВыбери режим (1-3): ").strip()
    
    if choice == "1":
        asyncio.run(main())
    elif choice == "2":
        asyncio.run(test_proxies_mode())
    else:
        print("Пока!")

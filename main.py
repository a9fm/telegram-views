#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import aiohttp
from aiohttp_socks import ProxyConnector
import re
import random
import os
from datetime import datetime
from fake_useragent import UserAgent
from pyppeteer import launch

# ============================================
# 📋 НАСТРОЙКИ
# ============================================
WORKING_FILE = "working.txt"
DEAD_FILE = "dead.txt"
POSTS_COUNT = 3
VIEWS_PER_POST = 5
CONCURRENCY = 3
PROXY_TIMEOUT = 5
BROWSER_TIMEOUT = 30000

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
        # Проверяем, есть ли уже
        existing = set()
        if os.path.exists(WORKING_FILE):
            with open(WORKING_FILE, "r", encoding='utf-8', errors='ignore') as f:
                existing = set(line.strip() for line in f if line.strip())
        
        if proxy_str not in existing:
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
# 🌐 ПАРСИНГ ПОСТОВ
# ============================================
async def get_last_posts(channel, count=POSTS_COUNT):
    """Получает последние посты канала"""
    url = f"https://t.me/s/{channel}"
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, timeout=10) as response:
                html = await response.text()
                
                # Ищем ID постов
                pattern1 = r'data-post="' + channel + r'/(\d+)"'
                pattern2 = r'href="/' + channel + r'/(\d+)"'
                
                post_ids = re.findall(pattern1, html)
                if not post_ids:
                    post_ids = re.findall(pattern2, html)
                
                # Убираем дубликаты и берем последние
                unique_ids = list(dict.fromkeys(post_ids))
                posts = [int(id) for id in unique_ids][-count:]
                
                log(f"📡 Найдено постов: {len(unique_ids)}, последние {count}: {posts}")
                return posts
                
        except Exception as e:
            log(f"❌ Ошибка парсинга канала: {e}")
            return []

# ============================================
# 🔍 ТЕСТИРОВАНИЕ ПРОКСИ
# ============================================
async def test_proxy(proxy_url: str, test_url: str):
    """Проверяет, работает ли прокси с Telegram"""
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
                    # Проверяем, что получили нормальный ответ
                    if "tgme_widget_message" in html or "tgme_page" in html:
                        return True
        return False
    except Exception:
        return False

async def test_proxies_batch(proxies, test_url, concurrency=50):
    """Тестирует пачку прокси"""
    log(f"🔍 Тестирование {len(proxies)} прокси...")
    
    semaphore = asyncio.Semaphore(concurrency)
    
    async def test_one(proxy):
        async with semaphore:
            stats['tested'] += 1
            if await test_proxy(proxy, test_url):
                save_working_proxy(proxy)
                return True
            else:
                save_dead_proxy(proxy)
                return False
    
    tasks = [test_one(proxy) for proxy in proxies]
    results = await asyncio.gather(*tasks)
    
    working = [p for p, r in zip(proxies, results) if r]
    log(f"✅ Тестирование завершено: {len(working)} рабочих из {len(proxies)}")
    return working

# ============================================
# 🎯 НАКРУТКА ПРОСМОТРОВ (PYPPETEER)
# ============================================
async def view_post_with_proxy(channel: str, post_id: int, proxy_url: str = None):
    """Открывает пост через pyppeteer с прокси"""
    url = f"https://t.me/{channel}/{post_id}"
    
    try:
        # Настройки запуска
        launch_options = {
            'headless': True,
            'args': [
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-accelerated-2d-canvas',
                '--disable-gpu'
            ]
        }
        
        # Добавляем прокси если есть
        if proxy_url:
            # Извлекаем тип и адрес
            if "://" in proxy_url:
                proxy_type, proxy_addr = proxy_url.split("://", 1)
                # pyppeteer понимает только http/s прокси
                if proxy_type in ['http', 'https', 'socks5']:
                    launch_options['args'].append(f'--proxy-server={proxy_url}')
            else:
                launch_options['args'].append(f'--proxy-server=http://{proxy_url}')
        
        # Запускаем браузер
        browser = await launch(**launch_options)
        
        # Создаем страницу
        page = await browser.newPage()
        
        # Устанавливаем User-Agent
        await page.setUserAgent(UserAgent().random)
        
        # Устанавливаем viewport
        await page.setViewport({
            'width': random.randint(1024, 1920),
            'height': random.randint(768, 1080)
        })
        
        # Переходим на пост
        await page.goto(url, {
            'waitUntil': 'domcontentloaded',
            'timeout': BROWSER_TIMEOUT
        })
        
        # Ждем загрузки
        await asyncio.sleep(random.randint(3, 6))
        
        # Скроллим
        await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
        await asyncio.sleep(random.randint(1, 2))
        
        # Еще ждем
        await asyncio.sleep(random.randint(2, 4))
        
        # Закрываем браузер
        await browser.close()
        
        stats['views_sent'] += 1
        update_progress()
        return True
            
    except Exception as e:
        log(f"❌ Ошибка просмотра {post_id} через {proxy_url}: {str(e)[:50]}")
        return False

async def run_views(channel: str, post_ids: list, working_proxies: list, views_per_post: int):
    """Запускает накрутку на все посты"""
    log(f"🚀 Запуск накрутки на {len(post_ids)} постов, {views_per_post} просмотров каждый")
    
    # Создаем список задач
    tasks = []
    for post_id in post_ids:
        for _ in range(views_per_post):
            proxy = random.choice(working_proxies) if working_proxies else None
            tasks.append(view_post_with_proxy(channel, post_id, proxy))
    
    # Запускаем с ограничением параллельности
    semaphore = asyncio.Semaphore(CONCURRENCY)
    
    async def run_with_limit(task):
        async with semaphore:
            return await task
    
    limited_tasks = [run_with_limit(task) for task in tasks]
    results = await asyncio.gather(*limited_tasks, return_exceptions=True)
    
    success = sum(1 for r in results if r is True)
    log(f"\n✅ Накрутка завершена: {success}/{len(tasks)} успешно")

# ============================================
# 🚀 ГЛАВНАЯ ФУНКЦИЯ
# ============================================
async def main():
    log("=" * 50)
    log("🤖 Telegram View Bot v2.0 (Pyppeteer)")
    log("=" * 50)
    
    # Ввод данных
    channel = input("📢 Введите название канала (без @): ").strip()
    if not channel:
        channel = "durov"
        log(f"⚠️ Использую канал @{channel}")
    
    # Получаем последние посты
    post_ids = await get_last_posts(channel, POSTS_COUNT)
    if not post_ids:
        log("❌ Не удалось получить посты!")
        return
    
    # Загружаем рабочие прокси
    working_proxies = load_working_proxies()
    
    if not working_proxies:
        log("⚠️ Нет рабочих прокси в файле!")
        want_test = input("🔍 Запустить тестирование прокси? (y/n): ").strip().lower()
        
        if want_test == 'y':
            # Здесь должен быть твой Auto класс для парсинга прокси
            # from auto import Auto
            # auto = Auto()
            # await auto.init()
            
            # Пока просто заглушка
            log("❌ Нужно добавить парсинг прокси")
            return
    
    if not working_proxies:
        log("❌ Нет рабочих прокси!")
        return
    
    log(f"✅ Использую {len(working_proxies)} рабочих прокси")
    
    # Запускаем накрутку
    await run_views(channel, post_ids, working_proxies, VIEWS_PER_POST)
    
    # Итог
    elapsed = (datetime.now() - stats['start_time']).total_seconds()
    log("\n" + "=" * 50)
    log("🏁 РАБОТА ЗАВЕРШЕНА")
    log(f"✅ Рабочих прокси: {stats['working']}")
    log(f"💀 Мертвых прокси: {stats['dead']}")
    log(f"👁️ Просмотров отправлено: {stats['views_sent']}")
    log(f"⏱️ Время работы: {elapsed:.1f}с")
    log("=" * 50)

# ============================================
# 🔧 КЛАСС AUTO (ЕСЛИ НУЖЕН)
# ============================================
class Auto:
    """Класс для парсинга прокси - вставь свой код"""
    def __init__(self):
        self.proxies = []
    
    async def init(self):
        # Твой код парсинга прокси
        pass

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log("\n🛑 Остановлено пользователем")
    except Exception as e:
        log(f"💥 Ошибка: {e}")

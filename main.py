import aiohttp
import asyncio
from re import search, compile
from argparse import ArgumentParser
from datetime import datetime
from fake_useragent import UserAgent
from aiohttp_socks import ProxyConnector
import os

# Regular expression for matching proxy patterns
REGEX = compile(
    r"(?:^|\D)?(("+ r"(?:[1-9]|[1-9]\d|1\d{2}|2[0-4]\d|25[0-5])"
    + r"\." + r"(?:\d|[1-9]\d|1\d{2}|2[0-4]\d|25[0-5])"
    + r"\." + r"(?:\d|[1-9]\d|1\d{2}|2[0-4]\d|25[0-5])"
    + r"\." + r"(?:\d|[1-9]\d|1\d{2}|2[0-4]\d|25[0-5])"
    + r"):" + (r"(?:\d|[1-9]\d{1,3}|[1-5]\d{4}|6[0-4]\d{3}"
    + r"|65[0-4]\d{2}|655[0-2]\d|6553[0-5])")
    + r")(?:\D|$)"
)

WORKING_FILE = "working.txt"

# Статистика
total_tested = 0
total_proxies = 0
working_count = 0
failed_count = 0
start_time = datetime.now()

def safe_str(text):
    """Безопасное преобразование в строку без ошибок кодировки"""
    if text is None:
        return ""
    try:
        if isinstance(text, bytes):
            return text.decode('utf-8', errors='replace')
        return str(text).encode('utf-8', errors='replace').decode('utf-8')
    except:
        return str(text).encode('ascii', errors='ignore').decode('ascii')

def log(message):
    timestamp = datetime.now().strftime("%H:%M:%S")
    safe_msg = safe_str(message)
    print(f"[{timestamp}] {safe_msg}")

def update_progress():
    """Обновляет прогресс в консоли"""
    global total_tested, total_proxies, working_count, failed_count, start_time
    remaining = total_proxies - total_tested
    percent = (total_tested / total_proxies * 100) if total_proxies > 0 else 0
    elapsed = (datetime.now() - start_time).total_seconds()
    speed = total_tested / elapsed if elapsed > 0 else 0
    
    print(f"\r📊 Прогресс: {total_tested}/{total_proxies} ({percent:.1f}%) | ✅ {working_count} | ❌ {failed_count} | ⚡ {speed:.1f}/с | Осталось: {remaining}   ", end="", flush=True)
    if total_tested >= total_proxies:
        print(f"\n✅ Все прокси протестированы за {elapsed:.1f}с! Средняя скорость: {speed:.1f} прокси/с")

def load_working_proxies():
    """Загружает список рабочих прокси из файла"""
    if not os.path.exists(WORKING_FILE):
        return []
    try:
        with open(WORKING_FILE, "r", encoding='utf-8', errors='ignore') as f:
            proxies = [line.strip() for line in f if line.strip()]
        log(f"Loaded {len(proxies)} working proxies from {WORKING_FILE}")
        return proxies
    except Exception as e:
        log(f"Error loading working proxies: {safe_str(e)}")
        return []

def save_working_proxy(proxy_str):
    """Сохраняет прокси в файл рабочих, если его там ещё нет"""
    global working_count
    if not proxy_str:
        return
    try:
        existing = set()
        if os.path.exists(WORKING_FILE):
            with open(WORKING_FILE, "r", encoding='utf-8', errors='ignore') as f:
                existing = set(line.strip() for line in f if line.strip())
        if proxy_str not in existing:
            with open(WORKING_FILE, "a", encoding='utf-8', errors='ignore') as f:
                f.write(proxy_str + "\n")
            working_count += 1
            log(f"💾 Saved working proxy: {proxy_str}")
        update_progress()
    except Exception as e:
        log(f"Error saving working proxy: {safe_str(e)}")

def remove_duplicates(proxies_list):
    """Удаляет дубликаты прокси (оставляет уникальные IP:port)"""
    unique = {}
    for proxy in proxies_list:
        if "://" in proxy:
            proxy_type, addr = proxy.split("://", 1)
        else:
            proxy_type, addr = "http", proxy
        unique[addr] = (proxy_type, addr)
    return [f"{pt}://{addr}" for pt, addr in unique.values()]

def remove_duplicates_auto(auto_proxies):
    """Удаляет дубликаты из списка кортежей (type, ip:port)"""
    seen = set()
    unique = []
    for pt, addr in auto_proxies:
        if addr not in seen:
            seen.add(addr)
            unique.append((pt, addr))
    return unique

class Telegram:
    def __init__(self, channel: str, post: int, concurrency: int = 500) -> None:
        self.channel = channel
        self.post = post
        self.concurrency = concurrency
        self.semaphore = asyncio.Semaphore(concurrency)
        log(f"Initialized with channel: @{channel}, post: {post}, concurrency: {concurrency}")

    async def request(self, proxy: str, proxy_type: str):
        global total_tested, failed_count
        proxy_url = f"{proxy_type}://{proxy}"
        try:
            async with self.semaphore:
                # Создаем connector без лишних проверок
                connector = ProxyConnector.from_url(proxy_url, rdns=True)
                
                # Используем один ClientSession на запрос с минимальными настройками
                async with aiohttp.ClientSession(connector=connector, cookie_jar=aiohttp.CookieJar(unsafe=True)) as session:
                    user_agent = UserAgent().random
                    headers = {
                        "referer": f"https://t.me/{self.channel}/{self.post}",
                        "user-agent": user_agent,
                    }
                    
                    # Уменьшаем таймаут до 3 секунд
                    async with session.get(
                        f"https://t.me/{self.channel}/{self.post}?embed=1&mode=tme",
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=3, connect=2),
                    ) as embed_response:

                        if not embed_response.cookies.get("stel_ssid"):
                            failed_count += 1
                            return

                        embed_text = await embed_response.text()
                        views_token = search('data-view="([^"]+)"', embed_text)

                        if not views_token:
                            failed_count += 1
                            return

                        async with session.post(
                            "https://t.me/v/?views=" + views_token.group(1),
                            headers={
                                "referer": f"https://t.me/{self.channel}/{self.post}?embed=1&mode=tme",
                                "user-agent": user_agent,
                                "x-requested-with": "XMLHttpRequest",
                            },
                            timeout=aiohttp.ClientTimeout(total=3),
                        ) as views_response:

                            views_text = await views_response.text()
                            if views_text == "true" and views_response.status == 200:
                                save_working_proxy(f"{proxy_type}://{proxy}")
                            else:
                                failed_count += 1

        except asyncio.CancelledError:
            pass
        except Exception:
            failed_count += 1
        finally:
            total_tested += 1
            update_progress()

    async def run_proxies_once(self, proxies_list, proxy_type):
        """Запускает один раунд тестирования всех прокси и завершается"""
        global total_proxies, start_time
        total_proxies = len(proxies_list)
        start_time = datetime.now()
        log(f"Starting test of {total_proxies} proxies of type {proxy_type}")
        
        # Создаем все задачи сразу без задержек
        tasks = [asyncio.create_task(self.request(proxy, proxy_type)) for proxy in proxies_list]
        
        try:
            await asyncio.gather(*tasks)
        except Exception as e:
            log(f"Error in run_proxies_once: {safe_str(e)}")
        
        elapsed = (datetime.now() - start_time).total_seconds()
        log(f"\n✅ Testing complete! Results: ✅ {working_count} | ❌ {failed_count} | Total: {total_tested} | Time: {elapsed:.1f}s")

    async def run_auto_once(self, proxies):
        """Запускает один раунд тестирования для auto режима"""
        global total_proxies, start_time
        total_proxies = len(proxies)
        start_time = datetime.now()
        log(f"Starting auto test of {total_proxies} proxies")
        
        # Создаем все задачи сразу
        tasks = [asyncio.create_task(self.request(proxy, pt)) for pt, proxy in proxies]
        
        try:
            await asyncio.gather(*tasks)
        except Exception as e:
            log(f"Error in auto mode: {safe_str(e)}")
        
        elapsed = (datetime.now() - start_time).total_seconds()
        log(f"\n✅ Auto test complete! Results: ✅ {working_count} | ❌ {failed_count} | Total: {total_tested} | Time: {elapsed:.1f}s")

class Auto:
    def __init__(self):
        self.proxies = []
        try:
            with open("auto/http.txt", "r") as file:
                self.http_sources = file.read().splitlines()
                log(f"Loaded {len(self.http_sources)} HTTP proxy sources")
                
            with open("auto/socks4.txt", "r") as file:
                self.socks4_sources = file.read().splitlines()
                log(f"Loaded {len(self.socks4_sources)} SOCKS4 proxy sources")
                
            with open("auto/socks5.txt", "r") as file:
                self.socks5_sources = file.read().splitlines()
                log(f"Loaded {len(self.socks5_sources)} SOCKS5 proxy sources")
                
        except FileNotFoundError as e:
            log(f"ERROR: Auto file not found - {safe_str(e)}")
            exit(0)
        
        log("Starting proxy scraping from sources...")

    async def scrap(self, source_url, proxy_type):
        try:
            async with aiohttp.ClientSession() as session:
                headers = {"user-agent": UserAgent().random}
                async with session.get(
                    source_url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    html = await response.text()
                    matches = REGEX.finditer(html)
                    found_proxies = [(proxy_type, match.group(1)) for match in matches]
                    self.proxies.extend(found_proxies)

        except Exception as e:
            try:
                with open("error.txt", "a", encoding="utf-8", errors="ignore") as f:
                    f.write(f"{source_url} -> {safe_str(e)}\n")
            except:
                pass

    async def init(self):
        tasks = []
        self.proxies.clear()
        sources_list = [
            (self.http_sources, "http"),
            (self.socks4_sources, "socks4"),
            (self.socks5_sources, "socks5"),
        ]

        for sources, proxy_type in sources_list:
            tasks.extend([self.scrap(source_url, proxy_type) for source_url in sources])

        await asyncio.gather(*tasks)
        
        original_count = len(self.proxies)
        self.proxies = remove_duplicates_auto(self.proxies)
        log(f"Proxy scraping complete. Found: {original_count} proxies, after dedup: {len(self.proxies)}")

async def main():
    global total_tested, total_proxies, working_count, failed_count, start_time
    
    parser = ArgumentParser()
    parser.add_argument("-c", "--channel", dest="channel", help="Channel user Without @ (e.g: MyChannel1234)", type=str, required=True)
    parser.add_argument("-pt", "--post", dest="post", help="Post number (ID) (e.g: 1921)", type=int, required=True)
    parser.add_argument("-t", "--type", dest="type", help="Proxy type (e.g: http)", type=str, required=False)
    parser.add_argument("-m", "--mode", dest="mode", help="Proxy mode (list | auto | rotate)", type=str, required=True)
    parser.add_argument("-p", "--proxy", dest="proxy", help="Proxy file path or user:password@host:port", type=str, required=False)
    parser.add_argument("-cc", "--concurrency", dest="concurrency", help="Maximum concurrent requests", type=int, default=500)
    args = parser.parse_args()
    
    log(f"Telegram Auto Views started with mode: {args.mode}")
    api = Telegram(args.channel, args.post, args.concurrency)
    
    # Загружаем рабочие прокси из файла
    working = load_working_proxies()
    
    if args.mode[0] == "l":  # list mode
        try:
            with open(args.proxy, "r", encoding='utf-8', errors='ignore') as file:
                file_proxies = file.read().splitlines()
            log(f"Loaded {len(file_proxies)} proxies from file {args.proxy}")
            
            file_proxies = remove_duplicates(file_proxies)
            log(f"After dedup: {len(file_proxies)} proxies")
            
            all_proxies = list(set(file_proxies + working))
            all_proxies = remove_duplicates(all_proxies)
            log(f"Total unique proxies after merging with working: {len(all_proxies)}")
            
            await api.run_proxies_once(all_proxies, args.type)
            
        except Exception as e:
            log(f"Error in list mode: {safe_str(e)}")

    elif args.mode[0] == "r":  # rotate mode
        log(f"Starting rotated mode with single proxy: {args.proxy}")
        await api.run_rotated_continuous(args.proxy, args.type)

    else:  # auto mode
        try:
            auto = Auto()
            await auto.init()
            
            auto_strings = [f"{pt}://{p}" for pt, p in auto.proxies]
            working_set = set(working)
            
            new_proxies = []
            for pt, p in auto.proxies:
                proxy_str = f"{pt}://{p}"
                if proxy_str not in working_set:
                    new_proxies.append((pt, p))
            
            log(f"New proxies from auto (not in working): {len(new_proxies)}")
            
            working_parsed = []
            for w in working:
                try:
                    if "://" in w:
                        pt, addr = w.split("://", 1)
                        working_parsed.append((pt, addr))
                    else:
                        working_parsed.append((args.type or "http", w))
                except:
                    continue
            
            working_parsed = remove_duplicates_auto(working_parsed)
            new_proxies = remove_duplicates_auto(new_proxies)
            
            all_proxies = working_parsed + new_proxies
            log(f"Total proxies to test: {len(all_proxies)}")
            
            if all_proxies:
                await api.run_auto_once(all_proxies)
            else:
                log("No proxies to run")
                
        except Exception as e:
            log(f"Fatal error in auto mode: {safe_str(e)}")

if __name__ == "__main__":
    log("Program started")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log("\n🛑 Program terminated by user")
    except Exception as e:
        log(f"Unhandled exception: {safe_str(e)}")

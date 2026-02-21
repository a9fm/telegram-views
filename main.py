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

def safe_str(text):
    """Безопасное преобразование в строку без ошибок кодировки"""
    if text is None:
        return ""
    try:
        # Пробуем заменить проблемные символы
        if isinstance(text, bytes):
            return text.decode('utf-8', errors='replace')
        return str(text).encode('utf-8', errors='replace').decode('utf-8')
    except:
        return str(text).encode('ascii', errors='ignore').decode('ascii')

def log(message):
    timestamp = datetime.now().strftime("%H:%M:%S")
    safe_msg = safe_str(message)
    print(f"[{timestamp}] {safe_msg}")

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
    if not proxy_str:
        return
    try:
        # Проверяем, есть ли уже
        existing = set()
        if os.path.exists(WORKING_FILE):
            with open(WORKING_FILE, "r", encoding='utf-8', errors='ignore') as f:
                existing = set(line.strip() for line in f if line.strip())
        if proxy_str not in existing:
            with open(WORKING_FILE, "a", encoding='utf-8', errors='ignore') as f:
                f.write(proxy_str + "\n")
            log(f"Saved working proxy: {proxy_str}")
    except Exception as e:
        log(f"Error saving working proxy: {safe_str(e)}")

class Telegram:
    def __init__(self, channel: str, post: int, concurrency: int = 100) -> None:
        self.channel = channel
        self.post = post
        self.concurrency = concurrency
        self.semaphore = asyncio.Semaphore(concurrency)
        log(f"Initialized with channel: @{channel}, post: {post}, concurrency: {concurrency}")

    async def request(self, proxy: str, proxy_type: str):
        proxy_url = f"{proxy_type}://{proxy}"
        try:
            async with self.semaphore:
                connector = ProxyConnector.from_url(proxy_url)
                jar = aiohttp.CookieJar(unsafe=True)
                async with aiohttp.ClientSession(cookie_jar=jar, connector=connector) as session:
                    user_agent = UserAgent().random
                    headers = {
                        "referer": f"https://t.me/{self.channel}/{self.post}",
                        "user-agent": user_agent,
                    }
                    async with session.get(
                        f"https://t.me/{self.channel}/{self.post}?embed=1&mode=tme",
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=5),
                    ) as embed_response:

                        if not jar.filter_cookies(embed_response.url).get("stel_ssid"):
                            log("ERROR: No cookies received")
                            return

                        embed_text = await embed_response.text()
                        views_token = search('data-view="([^"]+)"', embed_text)

                        if not views_token:
                            log("ERROR: No view token found")
                            return

                        views_response = await session.post(
                            "https://t.me/v/?views=" + views_token.group(1),
                            headers={
                                "referer": f"https://t.me/{self.channel}/{self.post}?embed=1&mode=tme",
                                "user-agent": user_agent,
                                "x-requested-with": "XMLHttpRequest",
                            },
                            timeout=aiohttp.ClientTimeout(total=5),
                        )

                        views_text = await views_response.text()
                        if views_text == "true" and views_response.status == 200:
                            log("SUCCESS: View sent")
                            save_working_proxy(f"{proxy_type}://{proxy}")
                        else:
                            log("FAILED: View not registered")

        except asyncio.CancelledError:
            log(f"Task cancelled for proxy {proxy_type}://{proxy}")
        except Exception as e:
            log(f"ERROR: Proxy connection failed - {proxy_type}://{proxy} - {safe_str(e)[:50]}...")
        finally:
            if 'jar' in locals():
                jar.clear()

    async def run_proxies_continuous(self, proxies_list, proxy_type):
        log(f"Starting continuous mode with {len(proxies_list)} proxies of type {proxy_type}")
        tasks = []
        for proxy in proxies_list:
            task = asyncio.create_task(self.continuous_request(proxy, proxy_type))
            tasks.append(task)
            await asyncio.sleep(0.1)  # Небольшая задержка при запуске
        
        try:
            await asyncio.gather(*tasks)
        except Exception as e:
            log(f"Error in run_proxies_continuous: {safe_str(e)}")

    async def continuous_request(self, proxy: str, proxy_type: str):
        while True:
            try:
                await self.request(proxy, proxy_type)
            except asyncio.CancelledError:
                break
            except Exception:
                pass
            await asyncio.sleep(1)

    async def run_auto_continuous(self, proxies):
        log(f"Starting continuous auto mode with {len(proxies)} proxies")
        tasks = []
        for proxy_type, proxy in proxies:
            task = asyncio.create_task(self.continuous_request(proxy, proxy_type))
            tasks.append(task)
            await asyncio.sleep(0.1)
        
        try:
            await asyncio.gather(*tasks)
        except Exception as e:
            log(f"Error in auto mode: {safe_str(e)}")

    async def run_rotated_continuous(self, proxy: str, proxy_type: str):
        log(f"Starting continuous rotated mode with proxy {proxy_type}://{proxy}")
        tasks = []
        for i in range(self.concurrency * 5):
            task = asyncio.create_task(self.continuous_request(proxy, proxy_type))
            tasks.append(task)
            await asyncio.sleep(0.05)
        
        try:
            await asyncio.gather(*tasks)
        except Exception as e:
            log(f"Error in rotated mode: {safe_str(e)}")

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
                log(f"Scraping {proxy_type} proxies from {source_url[:50]}...")
                async with session.get(
                    source_url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)
                ) as response:
                    html = await response.text()
                    matches = REGEX.finditer(html)
                    found_proxies = [(proxy_type, match.group(1)) for match in matches]
                    self.proxies.extend(found_proxies)
                    log(f"Found {len(found_proxies)} {proxy_type} proxies from {source_url[:30]}...")

        except Exception as e:
            log(f"ERROR: Failed to scrape from {source_url[:50]}... - {safe_str(e)[:100]}")
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
        log(f"Proxy scraping complete. Total proxies found: {len(self.proxies)}")

async def main():
    parser = ArgumentParser()
    parser.add_argument("-c", "--channel", dest="channel", help="Channel user Without @ (e.g: MyChannel1234)", type=str, required=True)
    parser.add_argument("-pt", "--post", dest="post", help="Post number (ID) (e.g: 1921)", type=int, required=True)
    parser.add_argument("-t", "--type", dest="type", help="Proxy type (e.g: http)", type=str, required=False)
    parser.add_argument("-m", "--mode", dest="mode", help="Proxy mode (list | auto | rotate)", type=str, required=True)
    parser.add_argument("-p", "--proxy", dest="proxy", help="Proxy file path or user:password@host:port", type=str, required=False)
    parser.add_argument("-cc", "--concurrency", dest="concurrency", help="Maximum concurrent requests", type=int, default=200)
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
            
            # Объединяем с рабочими, удаляем дубли
            all_proxies = list(set(file_proxies + working))
            log(f"Total unique proxies after merging with working: {len(all_proxies)}")
            
            await api.run_proxies_continuous(all_proxies, args.type)
        except Exception as e:
            log(f"Error in list mode: {safe_str(e)}")

    elif args.mode[0] == "r":  # rotate mode
        log(f"Starting rotated mode with single proxy: {args.proxy}")
        await api.run_rotated_continuous(args.proxy, args.type)

    else:  # auto mode
        try:
            # Парсим новые прокси
            auto = Auto()
            await auto.init()
            
            # Преобразуем спаршенные прокси в строки с типом
            auto_strings = [f"{pt}://{p}" for pt, p in auto.proxies]
            working_set = set(working)
            
            # Добавляем только те, которых нет в working
            new_proxies = []
            for pt, p in auto.proxies:
                proxy_str = f"{pt}://{p}"
                if proxy_str not in working_set:
                    new_proxies.append((pt, p))
            
            log(f"New proxies from auto (not in working): {len(new_proxies)}")
            
            # Рабочие строки имеют вид "type://ip:port", разбираем
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
            
            # Итоговый список для отправки
            all_proxies = working_parsed + new_proxies
            log(f"Total proxies to run: {len(all_proxies)}")
            
            if all_proxies:
                await api.run_auto_continuous(all_proxies)
            else:
                log("No proxies to run")
                
        except Exception as e:
            log(f"Fatal error in auto mode: {safe_str(e)}")

if __name__ == "__main__":
    log("Program started")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log("Program terminated by user")
    except Exception as e:
        log(f"Unhandled exception: {safe_str(e)}")

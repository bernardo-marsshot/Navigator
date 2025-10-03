
import re
import time
import random
import json
import os
import traceback
from decimal import Decimal
from typing import Optional, Tuple, Dict, Any, List
import requests
from bs4 import BeautifulSoup
from django.conf import settings
from .models import Retailer, SKUListing, PricePoint, SKU

# Advanced scraping libraries
import cloudscraper
try:
    from fake_useragent import UserAgent
    ua = UserAgent()
except:
    ua = None  # Fallback to default UA if fake_useragent fails

HEADERS_POOL = [
    {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"},
    {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"},
]

REALISTIC_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Cache-Control": "max-age=0",
    "DNT": "1",
}

CURRENCY_REGEX = re.compile(r"(?:Â)?([£$€])\s*([0-9]+(?:[.,][0-9]{2})?)", re.UNICODE)

# Global persistent scrapers with cookie jars (one per session)
_persistent_scrapers = {}

def get_persistent_scraper(retailer_name: str = "default"):
    """
    Get or create a persistent cloudscraper client for a retailer.
    Reuses cookies and session to avoid Cloudflare 403s.
    """
    global _persistent_scrapers
    
    if retailer_name not in _persistent_scrapers:
        scraper = cloudscraper.create_scraper()
        
        # Get User-Agent with fallback
        user_agent = ua.chrome if ua else 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        
        # Randomize headers slightly to avoid fingerprinting
        chrome_version = random.randint(119, 122)
        scraper.headers.update({
            'User-Agent': user_agent.replace('120.0.0.0', f'{chrome_version}.0.0.0'),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-GB,en-US;q=0.9,en;q=0.8',
            'Sec-Ch-Ua': f'"Not_A Brand";v="8", "Chromium";v="{chrome_version}"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
        })
        
        _persistent_scrapers[retailer_name] = scraper
        print(f"🔧 Created persistent scraper for {retailer_name}")
    
    return _persistent_scrapers[retailer_name]

def parse_price(text: str) -> Tuple[Optional[str], Optional[Decimal]]:
    if not text:
        return None, None
    m = CURRENCY_REGEX.search(text.replace(",", ""))
    if not m:
        # fallback: numbers only
        m2 = re.search(r"([0-9]+(?:[.][0-9]{2})?)", text.replace(",", ""))
        if not m2:
            return None, None
        return None, Decimal(m2.group(1))
    symbol, amount = m.groups()
    try:
        return symbol, Decimal(amount)
    except Exception:
        return symbol, None

def fetch(url: str) -> Optional[str]:
    try:
        headers = random.choice(HEADERS_POOL)
        resp = requests.get(url, headers=headers, timeout=20)
        if resp.status_code == 200:
            return resp.text
        print(f"⚠️ fetch() got status {resp.status_code} for {url}")
        return None
    except Exception as e:
        print(f"❌ fetch() failed for {url}")
        print(f"Error: {type(e).__name__}: {e}")
        print("Traceback:")
        traceback.print_exc()
        return None

def extract_price_from_json(html: str, url: str) -> Optional[tuple]:
    """
    Extract price from embedded JSON in HTML (for sites like Sainsbury's).
    Looks for window.__PRELOADED_STATE__ or application/ld+json.
    Returns (currency, price_decimal, price_text) or None
    """
    import re
    
    try:
        # Try Sainsbury's __PRELOADED_STATE__
        if 'sainsburys' in url.lower() or '__PRELOADED_STATE__' in html:
            preload_match = re.search(r'window\.__PRELOADED_STATE__\s*=\s*({.+?});', html, re.DOTALL)
            if preload_match:
                json_str = preload_match.group(1)
                data = json.loads(json_str)
                
                # Navigate through nested structure to find price
                try:
                    product_data = data.get('product', {}).get('productDetail', {})
                    price = product_data.get('price', {}).get('now')
                    if price:
                        price_val = float(price)
                        if 0.01 <= price_val <= 9999.99:
                            print(f"✅ Extracted price from __PRELOADED_STATE__: £{price_val}")
                            return ('£', Decimal(str(price_val)), f'£{price_val:.2f}')
                except (KeyError, TypeError, ValueError) as e:
                    print(f"⚠️ Error navigating __PRELOADED_STATE__: {e}")
        
        # Try application/ld+json (structured data)
        soup = BeautifulSoup(html, 'html.parser')
        json_ld_scripts = soup.find_all('script', type='application/ld+json')
        
        for script in json_ld_scripts:
            try:
                data = json.loads(script.string)
                
                # Handle array of objects
                if isinstance(data, list):
                    for item in data:
                        price = extract_price_from_json_ld(item)
                        if price:
                            return price
                else:
                    price = extract_price_from_json_ld(data)
                    if price:
                        return price
            except (json.JSONDecodeError, AttributeError):
                continue
        
    except Exception as e:
        print(f"⚠️ JSON extraction error: {e}")
    
    return None

def extract_price_from_json_ld(data: dict) -> Optional[tuple]:
    """Helper to extract price from JSON-LD structured data"""
    try:
        # Check for Product schema
        if data.get('@type') == 'Product':
            offers = data.get('offers', {})
            if isinstance(offers, list):
                offers = offers[0] if offers else {}
            
            price = offers.get('price') or offers.get('lowPrice')
            if price:
                price_val = float(price)
                if 0.01 <= price_val <= 9999.99:
                    currency = offers.get('priceCurrency', '£')
                    print(f"✅ Extracted price from JSON-LD: {currency}{price_val}")
                    return (currency, Decimal(str(price_val)), f'{currency}{price_val:.2f}')
    except (KeyError, TypeError, ValueError):
        pass
    
    return None

def extract_price_from_html_fallback(html: str, url: str) -> Optional[tuple]:
    """
    Fallback method to extract price from HTML when CSS selectors fail.
    Uses regex to find price patterns.
    Returns (currency, price_decimal, price_text) or None
    """
    import re
    
    # First try JSON extraction (better for modern sites)
    json_price = extract_price_from_json(html, url)
    if json_price:
        return json_price
    
    # Find all £X.XX patterns in the HTML
    price_patterns = [
        r'(?:Â)?£\s*([0-9]+\.[0-9]{2})',  # £3.15 or Â£3.15 (encoding issue)
        r'&pound;\s*([0-9]+\.[0-9]{2})',  # &pound;3.15
        r'["\']price["\']:\s*([0-9]+\.[0-9]{2})',  # "price": 3.15
    ]
    
    found_prices = []
    for pattern in price_patterns:
        matches = re.findall(pattern, html)
        for match in matches:
            try:
                price_val = float(match)
                # Filter out nonsense prices (0.00, very high numbers)
                if 0.01 <= price_val <= 9999.99:
                    found_prices.append(price_val)
            except:
                pass
    
    if found_prices:
        # Return the most common price (likely the actual product price)
        from collections import Counter
        price_counts = Counter(found_prices)
        most_common_price = price_counts.most_common(1)[0][0]
        return ('£', Decimal(str(most_common_price)), f'£{most_common_price:.2f}')
    
    return None

def scrape_with_httpx(url: str, cookies=None) -> Optional[str]:
    """
    Third fallback scraping method using httpx with HTTP/2.
    HTTP/2 can bypass some modern anti-bot systems.
    Can accept cookies from cloudscraper for better success rate.
    """
    try:
        import httpx
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-GB,en-US;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
            'DNT': '1',
        }
        
        time.sleep(random.uniform(1.5, 3.0))
        
        with httpx.Client(http2=True, follow_redirects=True, timeout=30.0, cookies=cookies) as client:
            response = client.get(url, headers=headers)
            
            if response.status_code == 200:
                html = response.text
                
                if len(html) < 500:
                    print(f"⚠️ httpx got suspiciously small response ({len(html)} bytes)")
                    return None
                
                html_lower = html.lower()
                if ('<title>just a moment' in html_lower or 
                    '<title>attention required' in html_lower or
                    'checking your browser' in html_lower):
                    print(f"⚠️ httpx detected challenge/blocked page")
                    return None
                
                print(f"✅ httpx (HTTP/2) successfully scraped {url} ({len(html)} bytes)")
                return html
            else:
                print(f"⚠️ httpx got status {response.status_code}")
                return None
                
    except ImportError:
        print(f"⚠️ httpx library not installed, skipping HTTP/2 method")
        return None
    except Exception as e:
        print(f"❌ httpx scraping failed for {url}")
        print(f"Error: {type(e).__name__}: {e}")
        return None

def scrape_with_selenium(url: str) -> Optional[str]:
    """Scrape URL using undetected-chromedriver to bypass anti-bot detection"""
    try:
        import undetected_chromedriver as uc
        import subprocess
        
        # Find Chrome/Chromium binary path
        chrome_path = '/nix/store/qa9cnw4v5xkxyip6mb9kxqfq1z4x2dx1-chromium-138.0.7204.100/bin/chromium-browser'
        try:
            # Try to get from environment if different
            result = subprocess.run(['which', 'chromium-browser'], capture_output=True, text=True, timeout=2)
            if result.returncode == 0 and result.stdout.strip():
                chrome_path = result.stdout.strip()
        except:
            pass
        
        # Create options for stealth mode
        options = uc.ChromeOptions()
        options.binary_location = chrome_path
        options.add_argument('--headless=new')  # New headless mode (more stable)
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1080')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        
        # Additional stealth settings
        options.add_argument('--disable-features=IsolateOrigins,site-per-process')
        
        # Copy chromedriver to writable location (undetected-chromedriver needs to patch it)
        chromedriver_path = '/tmp/chromedriver/chromedriver'
        if not os.path.exists(chromedriver_path):
            try:
                import shutil
                os.makedirs(os.path.dirname(chromedriver_path), exist_ok=True)
                result = subprocess.run(['which', 'chromedriver'], capture_output=True, text=True, timeout=2)
                if result.returncode == 0 and result.stdout.strip():
                    shutil.copy(result.stdout.strip(), chromedriver_path)
                    os.chmod(chromedriver_path, 0o755)
            except Exception as e:
                print(f"Warning: Could not copy chromedriver: {e}")
        
        # Initialize undetected chromedriver with explicit paths
        driver = uc.Chrome(
            options=options,
            driver_executable_path=chromedriver_path,
            use_subprocess=False,
            version_main=138  # Match the installed Chromium version
        )
        
        # Random delay before loading (human-like)
        time.sleep(random.uniform(1.0, 2.5))
        
        # Load the page
        driver.get(url)
        
        # Wait with random delay (simulate human reading)
        time.sleep(random.uniform(3.0, 5.0))
        
        # Simulate human-like scrolling
        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 3);")
            time.sleep(random.uniform(0.5, 1.0))
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 2);")
            time.sleep(random.uniform(0.5, 1.0))
        except:
            pass
        
        html = driver.page_source
        driver.quit()
        
        # Check if we got a Chrome error page (blocked/forbidden)
        if 'color-scheme' in html and 'chrome-error' in html.lower():
            print(f"⚠️ Selenium blocked/error page for {url}")
            return None
        
        # Check if we got actual content
        if len(html) < 5000:  # Tesco pages are usually >100KB
            print(f"⚠️ Suspiciously small response for {url}")
            return None
        
        print(f"✅ Successfully scraped {url} with undetected-chromedriver ({len(html)} bytes)")
        return html
    except Exception as e:
        print(f"❌ Selenium scraping failed for {url}")
        print(f"Error: {type(e).__name__}: {e}")
        print("Traceback:")
        traceback.print_exc()
        return None

def scrape_listing(listing: SKUListing) -> Optional[tuple]:
    """
    Scrape a listing and return (PricePoint, raw_html) tuple.
    Returns None if scraping fails.
    """
    if not listing.is_active or not listing.retailer.is_active:
        return None
    selectors = getattr(listing.retailer, "selectors", None)
    if not selectors:
        return None
    
    raw_html = None
    html = None
    
    # Use persistent cloudscraper with backoff for reliability
    scraper = get_persistent_scraper(listing.retailer.name)
    
    # Retry with exponential backoff for 403 errors
    max_retries = 3
    base_delay = 2.0
    
    for attempt in range(max_retries):
        try:
            # Add random delay (longer for Tesco)
            if listing.retailer.name == "Tesco":
                delay = random.uniform(2.0, 4.0) if attempt == 0 else base_delay * (2 ** attempt) + random.uniform(0, 2)
                time.sleep(delay)
            elif attempt > 0:
                time.sleep(base_delay * (2 ** attempt) + random.uniform(0, 1))
            
            response = scraper.get(listing.url, timeout=20)
            
            # Check status code
            if response.status_code == 403:
                print(f"⚠️ Attempt {attempt+1}/{max_retries}: Access denied (403 Forbidden)")
                if attempt < max_retries - 1:
                    print(f"   Retrying with backoff ({base_delay * (2 ** (attempt+1)):.1f}s)...")
                    continue
                html = None
            elif response.status_code != 200:
                print(f"⚠️ Got status {response.status_code} (expected 200)")
                html = None
                break
            else:
                html = response.text
                raw_html = html
                
                # Check for challenge/blocked/error pages
                html_lower = html.lower()
                if ('<title>just a moment' in html_lower or 
                    '<title>attention required' in html_lower or
                    '<title>error</title>' in html_lower or
                    'checking your browser' in html_lower or
                    'interstitial' in html_lower):
                    print(f"⚠️ Attempt {attempt+1}/{max_retries}: Challenge/error page detected")
                    if attempt < max_retries - 1:
                        print(f"   Retrying with backoff...")
                        html = None
                        continue
                    html = None
                    raw_html = None
                else:
                    print(f"   Cloudscraper got {len(html)} bytes (status {response.status_code})")
                    break
                    
        except Exception as e:
            print(f"❌ Attempt {attempt+1}/{max_retries}: Cloudscraper error: {type(e).__name__}: {e}")
            if attempt < max_retries - 1:
                print(f"   Retrying...")
                continue
            else:
                print("Falling back to simple fetch...")
                html = fetch(listing.url)
                raw_html = html
                break
    
    # Initialize price variables
    price = None
    promo_price = None
    currency = ""
    raw_snapshot = ""
    raw_price_text = ""
    raw_promo_text = ""
    
    # If cloudscraper failed, try httpx/selenium fallbacks immediately
    if not html:
        print(f"🔄 Cloudscraper exhausted, trying fallback methods...")
        
        # Try httpx with HTTP/2 (third scraping method) - share cookies from scraper
        print(f"🔄 Trying httpx with HTTP/2...")
        html = scrape_with_httpx(listing.url, cookies=scraper.cookies)
        if html:
            raw_html = html
            print(f"   httpx got {len(html)} bytes")
        
        # If httpx also failed, try Selenium
        if not html:
            print(f"🌐 Trying Selenium (JavaScript rendering)...")
            html = scrape_with_selenium(listing.url)
            if html:
                raw_html = html
                print(f"   Selenium got {len(html)} bytes")
        
        # If all methods failed, return None
        if not html:
            print(f"❌ All scraping methods failed")
            return None
    
    # Now we have HTML, process it
    soup = BeautifulSoup(html, "html.parser")
    
    # Try configured CSS selectors first
    price_el = soup.select_one(selectors.price_selector)
    promo_price_el = soup.select_one(selectors.promo_price_selector) if selectors.promo_price_selector else None
    promo_text_el = soup.select_one(selectors.promo_text_selector) if selectors.promo_text_selector else None

    raw_price_text = price_el.get_text(strip=True) if price_el else ""
    raw_promo_price_text = promo_price_el.get_text(strip=True) if promo_price_el else ""
    raw_promo_text = promo_text_el.get_text(strip=True) if promo_text_el else ""

    cur_sym, price = parse_price(raw_price_text)
    cur_sym2, promo_price = parse_price(raw_promo_price_text)
    currency = cur_sym or cur_sym2 or ""

    # If CSS selectors succeeded, set snapshot
    if price or promo_price:
        raw_snapshot = (raw_price_text or "") + " | promo: " + (raw_promo_price_text or "") + " | " + (raw_promo_text or "")
    else:
        # Try fallback extraction methods
        print(f"⚠️ CSS selectors failed, trying fallback extraction...")
        fallback_result = extract_price_from_html_fallback(html, listing.url)
        if fallback_result:
            currency, price, raw_price_text = fallback_result
            raw_snapshot = f"Fallback (JSON/regex): {raw_price_text}"
            print(f"✅ Price extracted via fallback: {currency}{price}")
        else:
            # No price found
            print(f"❌ No price extracted from HTML")
            time.sleep(random.uniform(0.5, 1.2))
            return (None, raw_html)

    pp = PricePoint.objects.create(
        sku_listing=listing,
        price=price,
        promo_price=promo_price,
        promo_text=raw_promo_text,
        raw_currency=currency,
        raw_snapshot=raw_snapshot,
    )
    # polite delay
    time.sleep(random.uniform(0.5, 1.2))
    return (pp, raw_html)

def scrape_tesco_search_cloudscraper(search_term: str = "paper tissue") -> List[Dict[str, Any]]:
    """Scrape Tesco search results using cloudscraper to bypass Cloudflare"""
    try:
        scraper = cloudscraper.create_scraper()
        # Get User-Agent with fallback
        try:
            from fake_useragent import UserAgent
            user_agent = UserAgent().chrome
        except:
            user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

        # Set realistic headers to bypass anti-bot
        scraper.headers.update({
            'User-Agent': user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-GB,en-US;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"Windows"',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })

        # Search URL for Tesco
        search_url = f"https://www.tesco.com/groceries/en-GB/search?query={search_term.replace(' ', '%20')}"
        print(f"Searching Tesco for: {search_term}")
        print(f"URL: {search_url}")

        response = scraper.get(search_url, timeout=30)
        print(f"Response status: {response.status_code}")

        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')

            # Look for Tesco product tiles (updated with real selectors)
            product_selectors = [
                '._64Yvfa_verticalTile',  # Real Tesco product tile selector
                '.product-tile',
                '.product-list__item',
                '[data-testid="product-tile"]',
                '.product-item',
                '.product-card',
            ]

            products = []
            product_elements = []
            for selector in product_selectors:
                product_elements = soup.select(selector)
                if product_elements:
                    print(f"Found {len(product_elements)} products with selector: {selector}")
                    break

            if not product_elements:
                # Try to find any elements with product-related content
                product_elements = soup.find_all(lambda tag: tag.name and 
                                                'product' in str(tag.get('class', '')) or
                                                'product' in str(tag.get('id', '')))
                print(f"Found {len(product_elements)} elements with 'product' in class/id")

            for element in product_elements[:5]:  # Limit to first 5 products
                try:
                    product_data = extract_product_data_from_element(element, search_url)
                    if product_data:
                        products.append(product_data)
                except Exception as e:
                    print(f"Error extracting product data: {e}")
                    continue

            return products

        print(f"Failed to access Tesco search: {response.status_code}")
        return []

    except Exception as e:
        print(f"Cloudscraper error: {e}")
        return []

def scrape_tesco_search_selenium(search_term: str = "paper tissue") -> List[Dict[str, Any]]:
    """Scrape Tesco search results using Selenium (fallback only, may not work in all environments)"""
    driver = None
    try:
        # Local imports to avoid module-level import errors if Selenium not available
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        
        print("Trying Selenium approach...")

        # Set up Chrome options
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-plugins")
        chrome_options.add_argument("--disable-images")
        chrome_options.add_argument("--disable-javascript")

        ua = UserAgent()
        chrome_options.add_argument(f"--user-agent={ua.chrome}")

        driver = webdriver.Chrome(options=chrome_options)
        driver.set_page_load_timeout(30)

        # Navigate to Tesco search
        search_url = f"https://www.tesco.com/groceries/en-GB/search?query={search_term.replace(' ', '%20')}"
        print(f"Navigating to: {search_url}")

        driver.get(search_url)

        # Wait for page to load
        time.sleep(5)

        # Try to find product elements
        product_selectors = [
            "//div[contains(@class, 'product')]",
            "//article[contains(@class, 'product')]", 
            "//li[contains(@class, 'product')]",
            "//*[contains(@data-testid, 'product')]"
        ]

        products = []
        for selector in product_selectors:
            try:
                elements = driver.find_elements(By.XPATH, selector)
                if elements:
                    print(f"Found {len(elements)} products with selector: {selector}")
                    for element in elements[:5]:
                        try:
                            product_data = extract_product_data_from_selenium_element(element, search_url)
                            if product_data:
                                products.append(product_data)
                        except Exception as e:
                            print(f"Error extracting product data: {e}")
                    break
            except Exception as e:
                print(f"Error with selector {selector}: {e}")

        return products

    except Exception as e:
        print(f"Selenium error: {e}")
        return []
    finally:
        if driver:
            driver.quit()

def extract_product_data_from_element(element, search_url: str) -> Optional[Dict[str, Any]]:
    """Extract product data from a BeautifulSoup element"""
    try:
        product_data = {
            "search_url": search_url,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "retailer": "Tesco",
            "search_term": "paper tissue"
        }

        # Try to find title (updated with real Tesco selectors)
        title_selectors = [
            '._64Yvfa_titleLink',  # Real Tesco title link selector
            '.product-tile__title',
            '.product-title', 
            'h2 a', 'h3 a', 'h4 a',
            '[data-testid="product-title"]',
            'a[href*="/products/"]'
        ]

        for selector in title_selectors:
            title_elem = element.select_one(selector)
            if title_elem:
                title = title_elem.get_text(strip=True) or title_elem.get('title', '')
                if title and len(title) > 3:  # Ensure meaningful title
                    product_data["title"] = title
                    break

        # Try to find price (updated approach for Tesco)
        # First try specific selectors, then search for £ symbols
        price_found = False
        price_selectors = [
            '.price',
            '.product-price',
            '[data-testid="price"]',
            '.cost',
            '.price-current',
            '.price-value'
        ]

        for selector in price_selectors:
            price_elem = element.select_one(selector)
            if price_elem:
                price_text = price_elem.get_text(strip=True)
                if price_text and '£' in price_text:
                    cur_sym, price = parse_price(price_text)
                    if price:
                        product_data["price"] = str(price)
                        product_data["currency"] = cur_sym or "£"
                        product_data["price_text"] = price_text
                        price_found = True
                        break

        # If no price found with selectors, search for £ symbols in the element
        if not price_found:
            all_text = element.get_text()
            import re
            price_matches = re.findall(r'£\s*([0-9]+(?:\.[0-9]{2})?)', all_text)
            if price_matches:
                try:
                    price_value = price_matches[0]
                    product_data["price"] = price_value
                    product_data["currency"] = "£"
                    product_data["price_text"] = f"£{price_value}"
                except:
                    pass

        # Try to find product URL (prioritize Tesco product links)
        url_selectors = [
            '._64Yvfa_titleLink',  # Real Tesco title link
            'a[href*="/products/"]',  # Tesco product URLs
            'a[href]'
        ]

        for selector in url_selectors:
            link_elem = element.select_one(selector)
            if link_elem:
                href = link_elem.get('href')
                if href:
                    if href.startswith('/'):
                        product_data["url"] = f"https://www.tesco.com{href}"
                    elif href.startswith('http'):
                        product_data["url"] = href
                    break

        # Only return if we found at least title or price
        if product_data.get("title") or product_data.get("price"):
            return product_data

        return None

    except Exception as e:
        print(f"Error extracting product data: {e}")
        return None

def extract_product_data_from_selenium_element(element, search_url: str) -> Optional[Dict[str, Any]]:
    """Extract product data from a Selenium WebElement"""
    try:
        product_data = {
            "search_url": search_url,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "retailer": "Tesco",
            "search_term": "paper tissue"
        }

        # Try to find title
        try:
            title = element.find_element(By.CSS_SELECTOR, ".product-tile__title, .product-title, h3, h4, h5").text.strip()
            if title:
                product_data["title"] = title
        except:
            try:
                title = element.get_attribute("title") or element.text.strip()
                if title and len(title) < 200:  # Reasonable title length
                    product_data["title"] = title
            except:
                pass

        # Try to find price
        try:
            price_elem = element.find_element(By.CSS_SELECTOR, ".price, .product-price, .cost")
            price_text = price_elem.text.strip()
            if price_text and '£' in price_text:
                cur_sym, price = parse_price(price_text)
                if price:
                    product_data["price"] = str(price)
                    product_data["currency"] = cur_sym or "£"
                    product_data["price_text"] = price_text
        except:
            pass

        # Try to find product URL
        try:
            link_elem = element.find_element(By.TAG_NAME, "a")
            href = link_elem.get_attribute("href")
            if href:
                product_data["url"] = href
        except:
            pass

        # Only return if we found at least title or price
        if product_data.get("title") or product_data.get("price"):
            return product_data

        return None

    except Exception as e:
        print(f"Error extracting product data from Selenium element: {e}")
        return None

def scrape_tesco_paper_tissue() -> List[Dict[str, Any]]:
    """Main function to scrape Tesco for paper tissue products"""
    print("=== Starting Tesco Paper Tissue Scraping ===")

    # Try cloudscraper first
    products = scrape_tesco_search_cloudscraper("paper tissue")

    if not products:
        print("Cloudscraper failed, trying Selenium...")
        products = scrape_tesco_search_selenium("paper tissue")

    if not products:
        print("All scraping methods failed!")
        return []

    print(f"Successfully scraped {len(products)} products")
    return products

def save_to_json(data: Dict[str, Any], filename: str = "TESCO.json") -> bool:
    """Save single scraped data to JSON file"""
    try:
        # Create full file path
        file_path = os.path.join(settings.BASE_DIR, filename)

        # Load existing data if file exists
        existing_data = []
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
            except:
                existing_data = []

        # Ensure existing_data is a list
        if not isinstance(existing_data, list):
            existing_data = [existing_data] if existing_data else []

        # Append new data
        existing_data.append(data)

        # Save updated data
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(existing_data, f, indent=2, ensure_ascii=False)

        print(f"Data saved to {file_path}")
        return True
    except Exception as e:
        print(f"Error saving to JSON: {e}")
        return False

def save_all_products_to_json(products: List[Dict[str, Any]], filename: str = "TESCO.json") -> bool:
    """Save all scraped products to single JSON file"""
    try:
        # Create full file path
        file_path = os.path.join(settings.BASE_DIR, filename)

        # Save all products directly to the file (overwrite existing)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(products, f, indent=2, ensure_ascii=False)

        print(f"All {len(products)} products saved to {file_path}")
        return True
    except Exception as e:
        print(f"Error saving all products to JSON: {e}")
        return False

def save_tesco_products_to_database(products: List[Dict[str, Any]]) -> List[PricePoint]:
    """Save multiple Tesco products to database"""
    saved_price_points = []

    try:
        # Get or create Tesco retailer
        retailer, created = Retailer.objects.get_or_create(
            name="Tesco",
            defaults={
                "base_url": "https://www.tesco.com",
                "is_active": True
            }
        )

        for product_data in products:
            try:
                # Create unique SKU code based on title or URL
                title = product_data.get("title", "Unknown Product")
                url = product_data.get("url", "")

                # Generate unique SKU code
                if url:
                    sku_id = url.split('/')[-1] or url.split('/')[-2]
                else:
                    sku_id = re.sub(r'[^a-zA-Z0-9]', '', title.lower())[:20]

                sku_code = f"TESCO-{sku_id}"

                # Get or create SKU
                sku, created = SKU.objects.get_or_create(
                    code=sku_code,
                    defaults={
                        "name": title,
                        "competitor_names": ""
                    }
                )

                # Get or create SKU listing
                listing, created = SKUListing.objects.get_or_create(
                    sku=sku,
                    retailer=retailer,
                    url=url or product_data.get("search_url", ""),
                    defaults={"is_active": True}
                )

                # Create price point
                price = None
                promo_price = None

                if product_data.get("price"):
                    try:
                        price = Decimal(product_data["price"])
                    except:
                        pass

                if product_data.get("promo_price"):
                    try:
                        promo_price = Decimal(product_data["promo_price"])
                    except:
                        pass

                price_point = PricePoint.objects.create(
                    sku_listing=listing,
                    price=price,
                    promo_price=promo_price,
                    promo_text=product_data.get("promo_price_text", ""),
                    raw_currency=product_data.get("currency", "£"),
                    raw_snapshot=json.dumps(product_data, ensure_ascii=False)
                )

                saved_price_points.append(price_point)
                print(f"Saved price point to database: {price_point}")

            except Exception as e:
                print(f"Error saving product to database: {e}")
                continue

        return saved_price_points

    except Exception as e:
        print(f"Error in save_tesco_products_to_database: {e}")
        return []

def generate_sku_code(retailer_name: str, product_title: str) -> str:
    """Generate unique SKU code from retailer and product title"""
    clean_title = re.sub(r'[^\w\s-]', '', product_title.lower())
    words = clean_title.split()[:3]
    retailer_prefix = retailer_name[:4].upper().replace("'", "")
    title_part = '-'.join(words)[:20]
    base_code = f"{retailer_prefix}-{title_part}"
    
    code = base_code
    counter = 1
    while SKU.objects.filter(code=code).exists():
        code = f"{base_code}-{counter}"
        counter += 1
    
    return code


def discover_and_add_products(search_term: str = "paper tissue", max_products: int = 5) -> Dict[str, int]:
    """
    Discover and add new products from all active retailers
    Returns dict with counts of added SKUs and scraped prices
    """
    from pricing.models import Retailer
    
    added_count = 0
    scraped_count = 0
    
    retailers = Retailer.objects.filter(is_active=True)
    
    for retailer in retailers:
        products = []
        
        # Discover products based on retailer
        if retailer.name == 'Tesco':
            products = scrape_tesco_search_cloudscraper(search_term)
            if not products:
                products = scrape_tesco_search_selenium(search_term)
        
        # Add products to database
        for product in products[:max_products]:
            try:
                title = product.get('title', '')
                url = product.get('url', '')
                price_str = product.get('price', '')
                currency = product.get('currency', '£')
                
                if not title or not url:
                    continue
                
                # Generate SKU code
                sku_code = generate_sku_code(retailer.name, title)
                
                # Create or get SKU
                sku, sku_created = SKU.objects.get_or_create(
                    code=sku_code,
                    defaults={'name': title}
                )
                
                if sku_created:
                    added_count += 1
                
                # Create or get listing
                listing, listing_created = SKUListing.objects.get_or_create(
                    sku=sku,
                    retailer=retailer,
                    url=url,
                    defaults={'is_active': True}
                )
                
                # Create price point
                if price_str:
                    cur_sym, price_decimal = parse_price(f"{currency}{price_str}")
                    if price_decimal:
                        PricePoint.objects.create(
                            sku_listing=listing,
                            price=price_decimal,
                            raw_currency=cur_sym or currency,
                            raw_snapshot=f"Auto-discovered: {title}"
                        )
                        scraped_count += 1
                        
            except Exception as e:
                print(f"Error adding product: {e}")
                continue
    
    return {'added': added_count, 'scraped': scraped_count}


def run_scrape_for_all_active() -> dict:
    """
    Scrape prices for all active SKU listings.
    Only updates prices for existing products - does NOT discover new products.
    For product discovery, use the discover_products management command.
    
    Saves scraping results to 'extração.json' file.
    
    Returns:
        dict with 'count' (successful scrapes) and 'failed_retailers' (list of retailer names that failed)
    """
    import json
    from datetime import datetime
    
    count = 0
    failed_retailers = set()
    scraping_results = {}
    
    qs = SKUListing.objects.select_related("retailer", "sku").filter(is_active=True, retailer__is_active=True)
    
    for listing in qs:
        result_entry = {
            'timestamp': datetime.now().isoformat(),
            'retailer': listing.retailer.name,
            'product': listing.sku.name,
            'url': listing.url,
            'status': 'failed',
            'price': None,
            'currency': None,
            'error': None,
            'raw_information': None
        }
        
        try:
            print(f"\n🔍 Scraping: {listing.retailer.name} - {listing.sku.name}")
            print(f"   URL: {listing.url}")
            scrape_result = scrape_listing(listing)
            if scrape_result:
                pp, raw_html = scrape_result
                if pp:
                    # Successfully extracted price
                    print(f"✅ Success: {pp.raw_currency}{pp.price}")
                    result_entry['status'] = 'success'
                    result_entry['price'] = float(pp.price)
                    result_entry['currency'] = pp.raw_currency
                    result_entry['raw_information'] = raw_html
                    count += 1
                else:
                    # Got HTML but failed to extract price
                    print(f"❌ Failed: No price extracted")
                    result_entry['error'] = 'No price extracted'
                    result_entry['raw_information'] = raw_html
                    failed_retailers.add(listing.retailer.name)
            else:
                print(f"❌ Failed: No HTML retrieved")
                result_entry['error'] = 'No HTML retrieved'
                failed_retailers.add(listing.retailer.name)
        except Exception as e:
            print(f"❌ Exception while scraping listing {listing.id}:")
            print(f"   Retailer: {listing.retailer.name}")
            print(f"   SKU: {listing.sku.name}")
            print(f"   URL: {listing.url}")
            print(f"Error: {type(e).__name__}: {e}")
            print("Traceback:")
            traceback.print_exc()
            result_entry['error'] = f"{type(e).__name__}: {str(e)}"
            failed_retailers.add(listing.retailer.name)
        
        scraping_results[listing.sku.name] = result_entry
    
    # Save results to JSON file
    json_filename = 'extração.json'
    try:
        with open(json_filename, 'w', encoding='utf-8') as f:
            json.dump({
                'scraping_date': datetime.now().isoformat(),
                'total_scraped': count,
                'total_attempts': len(scraping_results),
                'results': scraping_results
            }, f, ensure_ascii=False, indent=2)
        print(f"\n💾 Results saved to '{json_filename}'")
    except Exception as e:
        print(f"\n⚠️ Error saving to JSON: {e}")
    
    return {'count': count, 'failed_retailers': list(failed_retailers)}

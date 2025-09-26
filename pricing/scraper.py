
import re
import time
import random
import json
import os
from decimal import Decimal
from typing import Optional, Tuple, Dict, Any, List
import requests
from bs4 import BeautifulSoup
from django.conf import settings
from .models import Retailer, SKUListing, PricePoint, SKU

# Advanced scraping libraries
import cloudscraper
from fake_useragent import UserAgent
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

HEADERS_POOL = [
    {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"},
    {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"},
]

TESCO_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Cache-Control": "max-age=0",
}

CURRENCY_REGEX = re.compile(r"([£$€])\s*([0-9]+(?:[.,][0-9]{{2}})?)", re.UNICODE)

def parse_price(text: str) -> Tuple[Optional[str], Optional[Decimal]]:
    if not text:
        return None, None
    m = CURRENCY_REGEX.search(text.replace(",", ""))
    if not m:
        # fallback: numbers only
        m2 = re.search(r"([0-9]+(?:[.][0-9]{{2}})?)", text.replace(",", ""))
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
        return None
    except Exception:
        return None

def scrape_listing(listing: SKUListing) -> Optional[PricePoint]:
    if not listing.is_active or not listing.retailer.is_active:
        return None
    selectors = getattr(listing.retailer, "selectors", None)
    if not selectors:
        return None
    html = fetch(listing.url)
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")
    price_el = soup.select_one(selectors.price_selector)
    promo_price_el = soup.select_one(selectors.promo_price_selector) if selectors.promo_price_selector else None
    promo_text_el = soup.select_one(selectors.promo_text_selector) if selectors.promo_text_selector else None

    raw_price_text = price_el.get_text(strip=True) if price_el else ""
    raw_promo_price_text = promo_price_el.get_text(strip=True) if promo_price_el else ""
    raw_promo_text = promo_text_el.get_text(strip=True) if promo_text_el else ""

    cur_sym, price = parse_price(raw_price_text)
    cur_sym2, promo_price = parse_price(raw_promo_price_text)
    currency = cur_sym or cur_sym2 or ""

    if not price and not promo_price and not raw_promo_text:
        return None

    pp = PricePoint.objects.create(
        sku_listing=listing,
        price=price,
        promo_price=promo_price,
        promo_text=raw_promo_text,
        raw_currency=currency,
        raw_snapshot=(raw_price_text or "") + " | promo: " + (raw_promo_price_text or "") + " | " + (raw_promo_text or ""),
    )
    # polite delay
    time.sleep(random.uniform(0.5, 1.2))
    return pp

def scrape_tesco_search_cloudscraper(search_term: str = "paper tissue") -> List[Dict[str, Any]]:
    """Scrape Tesco search results using cloudscraper to bypass Cloudflare"""
    try:
        scraper = cloudscraper.create_scraper()
        ua = UserAgent()
        
        # Set realistic headers
        scraper.headers.update({
            'User-Agent': ua.chrome,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-GB,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
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
    """Scrape Tesco search results using Selenium"""
    driver = None
    try:
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

def run_scrape_for_all_active() -> int:
    count = 0
    
    # Scrape Tesco for paper tissue products
    print("=== Starting Tesco Paper Tissue Scraping ===")
    tesco_products = scrape_tesco_paper_tissue()
    
    if tesco_products:
        print(f"Found {len(tesco_products)} Tesco products")
        
        # Save ALL products to single TESCO.json file as requested
        save_all_products_to_json(tesco_products, "TESCO.json")
        
        # Save all products to database
        price_points = save_tesco_products_to_database(tesco_products)
        count += len(price_points)
        
        if price_points:
            print(f"Successfully scraped and saved {len(price_points)} Tesco products!")
        else:
            print("Failed to save products to database")
    else:
        print("No Tesco products found!")
    
    # Then run existing scraper for other active listings
    qs = SKUListing.objects.select_related("retailer").filter(is_active=True, retailer__is_active=True)
    for listing in qs:
        if listing.retailer.name != "Tesco":  # Avoid duplicating Tesco scraping
            pp = scrape_listing(listing)
            if pp:
                count += 1
    
    return count

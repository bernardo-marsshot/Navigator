
import re
import time
import random
from decimal import Decimal
from typing import Optional, Tuple
import requests
from bs4 import BeautifulSoup
from .models import Retailer, SKUListing, PricePoint

HEADERS_POOL = [
    {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"},
    {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"},
]

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

def run_scrape_for_all_active() -> int:
    count = 0
    qs = SKUListing.objects.select_related("retailer").filter(is_active=True, retailer__is_active=True)
    for listing in qs:
        pp = scrape_listing(listing)
        if pp:
            count += 1
    return count

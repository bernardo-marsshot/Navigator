# pricing/scraper.py
from __future__ import annotations
import re
import time
import random
from decimal import Decimal
from typing import Optional, Dict, Callable, List, Tuple
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from django.db import transaction

try:
    import cloudscraper
    from fake_useragent import UserAgent
    CLOUDSCRAPER_AVAILABLE = True
except ImportError:
    CLOUDSCRAPER_AVAILABLE = False

from .models import Retailer, SKUListing, PricePoint

# -------- Configurações globais --------
HEADERS_POOL = [
    {
        "User-Agent":
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
    },
    {
        "User-Agent":
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
    },
]
CURRENCY_REGEX = re.compile(r"([£$€])\s*([0-9]+(?:[.,][0-9]{1,2})?)",
                            re.UNICODE)

# Rate limit simples (educado). Para produção, usar um scheduler (Celery).
DEFAULT_DELAY_SEC = (0.8, 1.8)

# Registry opcional de handlers por domínio (caso precises de lógica especial)
# Key: domínio (ex.: "amazon.co.uk"), Value: callable(listing) -> dict|None
RETAILER_HANDLER_REGISTRY: Dict[str, Callable[[SKUListing],
                                              Optional[dict]]] = {}

# Função para registrar handlers após serem definidos
def _register_handlers():
    """Registra handlers específicos após serem definidos"""
    RETAILER_HANDLER_REGISTRY.update({
        "www.tesco.com": scrape_tesco,
        "tesco.com": scrape_tesco,
    })


# -------- Utils --------
def _rand_delay(bounds: Tuple[float, float] = DEFAULT_DELAY_SEC):
    time.sleep(random.uniform(*bounds))


def parse_price(text: str) -> Tuple[Optional[str], Optional[Decimal]]:
    if not text:
        return None, None
    # normalizar separadores
    t = text.replace(",", "")
    m = CURRENCY_REGEX.search(t)
    if m:
        symbol, amount = m.groups()
        try:
            return symbol, Decimal(amount)
        except Exception:
            return symbol, None
    # fallback: números soltos
    m2 = re.search(r"([0-9]+(?:[.][0-9]{1,2})?)", t)
    if m2:
        try:
            return None, Decimal(m2.group(1))
        except Exception:
            return None, None
    return None, None


def fetch(url: str, timeout: int = 25, max_retries: int = 2) -> Optional[str]:
    """
    Fetch simples com cabeçalhos rotativos e 2 tentativas.
    Para páginas JS heavy, numa fase 2 integramos Playwright.
    """
    last_err = None
    for attempt in range(1, max_retries + 1):
        try:
            headers = random.choice(HEADERS_POOL)
            resp = requests.get(url, headers=headers, timeout=timeout)
            if resp.status_code == 200 and resp.text:
                return resp.text
            # status != 200 -> tentar de novo (mas sem martelar)
            _rand_delay((1.0, 2.2))
        except Exception as e:
            last_err = e
            _rand_delay((1.0, 2.2))
    # Falhou
    return None


def extract_with_selectors(soup: BeautifulSoup, selector: str) -> str:
    if not selector:
        return ""
    el = soup.select_one(selector)
    return el.get_text(strip=True) if el else ""


def domain_from_url(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""


# -------- Fallback universal por seletores CSS --------
def scrape_via_selectors(listing: SKUListing) -> Optional[dict]:
    """
    Leitura genérica: usa os seletores CSS configurados para o retalhista.
    """
    selectors = getattr(listing.retailer, "selectors", None)
    if not selectors:
        return None

    html = fetch(listing.url)
    if not html:
        return None

    soup = BeautifulSoup(html, "html.parser")

    raw_price_text = extract_with_selectors(soup, selectors.price_selector)
    raw_promo_price_text = extract_with_selectors(
        soup, selectors.promo_price_selector
    ) if selectors.promo_price_selector else ""
    raw_promo_text = extract_with_selectors(
        soup,
        selectors.promo_text_selector) if selectors.promo_text_selector else ""

    cur_sym, price = parse_price(raw_price_text)
    cur_sym2, promo_price = parse_price(raw_promo_price_text)
    currency = cur_sym or cur_sym2 or ""

    # Título opcional (útil para auditoria ou debug)
    title = ""
    t_el = soup.find("h1") or soup.select_one(
        "h1, .product-title, .pdp-product-name, [data-testid*=title]")
    if t_el:
        title = t_el.get_text(strip=True)[:250]

    # Se nada foi encontrado, desistir
    if not price and not promo_price and not raw_promo_text:
        return None

    return {
        "status": "success",
        "url": listing.url,
        "retailer": listing.retailer.name,
        "title": title,
        "price": price,  # Decimal | None
        "promo_price": promo_price,  # Decimal | None
        "promo_text": raw_promo_text or "",
        "currency": currency or "",
        "snapshot":
        f"{raw_price_text} | promo: {raw_promo_price_text} | {raw_promo_text}",
        "method": "css_selectors_fallback"
    }


# -------- Tesco Handler (search-based) --------
def scrape_tesco(listing: SKUListing) -> Optional[dict]:
    """
    Handler específico para Tesco usando pesquisa em vez de página direta.
    URLs diretas do Tesco são frequentemente bloqueadas, então pesquisamos pelo produto.
    """
    if not CLOUDSCRAPER_AVAILABLE:
        return {
            "status": "failed",
            "error": "cloudscraper not installed",
            "url": listing.url
        }
    
    try:
        # Extrair ID do produto da URL para match preciso
        product_id = listing.url.rstrip('/').split('/')[-1]
        
        # Termos de pesquisa baseados no nome do SKU
        search_terms = ["toilet tissue", "tissue paper", "toilet paper"]
        if hasattr(listing.sku, 'name'):
            sku_words = listing.sku.name.lower().split()
            if any(word in sku_words for word in ['andrex', 'cushelle', 'tesco']):
                search_terms.insert(0, ' '.join(sku_words[:2]))
        
        scraper = cloudscraper.create_scraper()
        ua = UserAgent()
        
        scraper.headers.update({
            'User-Agent': ua.chrome,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-GB,en;q=0.5',
            'DNT': '1',
        })
        
        # Tentar múltiplos termos de pesquisa
        for search_term in search_terms[:2]:  # Limitar a 2 tentativas
            try:
                url = f"https://www.tesco.com/groceries/en-GB/search?query={search_term.replace(' ', '+')}"
                response = scraper.get(url, timeout=20)
                
                if response.status_code != 200:
                    continue
                
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Procurar produtos na página de resultados
                products = soup.select('li[class*="product-list"], div[class*="product-tile"], article')
                
                for product_elem in products[:50]:  # Limitar verificação
                    # Procurar link do produto
                    link = product_elem.select_one('a[href*="/products/"]')
                    if not link:
                        continue
                    
                    href = link.get('href', '')
                    # Match pelo ID do produto
                    if product_id not in href:
                        continue
                    
                    # Extrair título
                    title_elem = product_elem.select_one('h3, [class*="title"], [data-auto*="title"]')
                    title = title_elem.get_text(strip=True) if title_elem else ""
                    
                    # Extrair preço - tentar múltiplos seletores
                    price_text = ""
                    price_selectors = [
                        '[data-auto*="price-value"]',
                        '[class*="price"]',
                        'span.value',
                        'p[class*="price"]'
                    ]
                    
                    for selector in price_selectors:
                        price_elem = product_elem.select_one(selector)
                        if price_elem:
                            price_text = price_elem.get_text(strip=True)
                            break
                    
                    if not price_text:
                        continue
                    
                    # Parse do preço
                    cur_sym, price = parse_price(price_text)
                    
                    if price and price > 0 and title:
                        return {
                            "status": "success",
                            "url": listing.url,
                            "retailer": "Tesco",
                            "title": title[:250],
                            "price": price,
                            "promo_price": None,
                            "promo_text": "",
                            "currency": cur_sym or "£",
                            "snapshot": f"Found via search: {search_term} | {price_text}",
                            "method": "tesco_search"
                        }
                
                # Delay entre pesquisas
                time.sleep(2)
                
            except Exception as e:
                continue
        
        return {
            "status": "failed",
            "error": f"Product {product_id} not found in search results",
            "url": listing.url
        }
        
    except Exception as e:
        return {
            "status": "failed",
            "error": str(e),
            "url": listing.url
        }


# -------- Handler dispatcher --------
def scrape_listing(listing: SKUListing) -> Optional[dict]:
    """
    Orquestra scraping para UM listing:
    1) Se houver handler específico para o domínio, usa-o.
    2) Caso contrário, usa o fallback por seletores CSS do RetailerSelector.
    """
    if not listing.is_active or not listing.retailer.is_active:
        return None

    dom = domain_from_url(listing.url)
    handler = RETAILER_HANDLER_REGISTRY.get(dom)

    if handler:
        result = handler(listing)
        if result and result.get("status") == "success":
            return result
        # Se handler não conseguiu, tenta fallback por seletores
        _rand_delay()
        fb = scrape_via_selectors(listing)
        if fb:
            return fb
        return result  # devolve erro do handler

    # Sem handler → universal selectors
    return scrape_via_selectors(listing)


# -------- Execução: todos os listings ativos --------
def run_scrape_for_all_active(
        rate_limit: Tuple[float, float] = DEFAULT_DELAY_SEC) -> int:
    """
    Percorre todos os SKUListing ativos e cria PricePoints quando encontra preço válido.
    Retorna o número de PricePoints criados.
    """
    created = 0
    qs = (SKUListing.objects.select_related("retailer").filter(
        is_active=True, retailer__is_active=True))

    for listing in qs:
        try:
            data = scrape_listing(listing)
            if not data or data.get("status") != "success":
                continue

            # Guardar na BD: preferir promo_price se existir (mas guardamos ambos)
            price = data.get("price")
            promo_price = data.get("promo_price")
            promo_text = (data.get("promo_text") or "")[:255]
            raw_currency = (data.get("currency") or "")[:10]
            raw_snapshot = (data.get("snapshot") or "")[:4000]

            # Validação mínima
            if (price is None and promo_price is None):
                continue
            if price is not None and price <= 0:
                price = None
            if promo_price is not None and promo_price <= 0:
                promo_price = None
            if price is None and promo_price is None:
                continue

            with transaction.atomic():
                PricePoint.objects.create(
                    sku_listing=listing,
                    price=price,
                    promo_price=promo_price,
                    promo_text=promo_text,
                    raw_currency=raw_currency,
                    raw_snapshot=raw_snapshot,
                )
                created += 1

        except Exception:
            # manter o scraper resiliente: ignora erro e segue
            pass
        finally:
            _rand_delay(rate_limit)

    return created


# Registrar handlers ao carregar módulo
_register_handlers()

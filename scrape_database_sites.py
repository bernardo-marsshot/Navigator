#!/usr/bin/env python
"""
Script para fazer scraping de todos os sites da base de dados
"""

import os
import sys
import django
import json
import time
from datetime import datetime
from typing import List, Dict, Any

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'navintelligence_mvp.settings')
django.setup()

from pricing.models import Retailer, SKU, SKUListing, PricePoint
from pricing.scraper import (
    scrape_tesco_search_cloudscraper, 
    extract_product_data_from_element,
    parse_price,
    scrape_tesco_paper_tissue
)

# Advanced scraping libraries
import cloudscraper
from fake_useragent import UserAgent
from bs4 import BeautifulSoup
import requests
from decimal import Decimal
import re
import time
from functools import lru_cache


# Cache para evitar múltiplas pesquisas desnecessárias
@lru_cache(maxsize=32)
def cached_tesco_search(search_term: str, max_products: int = 50) -> List[Dict[str, Any]]:
    """Cache pesquisas Tesco expandidas para evitar requests repetidos"""
    return comprehensive_tesco_search(search_term, max_products)


def comprehensive_tesco_search(search_term: str, max_products: int = 50) -> List[Dict[str, Any]]:
    """
    Pesquisa abrangente do Tesco que obtém muito mais produtos
    """
    all_products = []

    try:
        # Usar cloudscraper para contornar proteções
        scraper = cloudscraper.create_scraper()
        ua = UserAgent()

        scraper.headers.update({
            'User-Agent': ua.chrome,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-GB,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })

        base_url = "https://www.tesco.com/groceries/en-GB/search"
        page = 1
        products_found = 0

        while products_found < max_products and page <= 5:  # Limitar a 5 páginas para evitar abusos
            try:
                # Construir URL com paginação 
                params = {
                    'query': search_term,
                    'page': page
                }

                url = f"{base_url}?{'&'.join([f'{k}={v}' for k, v in params.items()])}"
                print(f"🔍 Searching Tesco page {page}: {search_term}")

                response = scraper.get(url, timeout=30)

                if response.status_code != 200:
                    print(f"⚠️  HTTP {response.status_code} on page {page}")
                    break

                soup = BeautifulSoup(response.text, 'html.parser')

                # Encontrar produtos na página
                product_tiles = soup.select('._64Yvfa_verticalTile')

                if not product_tiles:
                    print(f"⚠️  No products found on page {page}")
                    break

                page_products = []
                for tile in product_tiles:
                    try:
                        product_data = extract_product_data_from_element(tile, url)
                        if product_data and product_data.get("title") and product_data.get("price"):
                            page_products.append(product_data)
                            products_found += 1

                            if products_found >= max_products:
                                break

                    except Exception as e:
                        print(f"⚠️  Error extracting product data: {e}")
                        continue

                if page_products:
                    all_products.extend(page_products)
                    print(f"✅ Found {len(page_products)} products on page {page} (total: {len(all_products)})")
                else:
                    print(f"⚠️  No valid products extracted from page {page}")
                    break

                # Se a página retornou menos produtos que o esperado, provavelmente é a última
                if len(page_products) < 10:  # Assumindo ~24 produtos por página normalmente
                    print(f"ℹ️  Fewer products on page {page}, likely last page")
                    break

                page += 1

                # Delay entre páginas para ser respeitoso
                time.sleep(2)

            except Exception as e:
                print(f"⚠️  Error on page {page}: {e}")
                break

        print(f"🎯 Comprehensive search for '{search_term}' found {len(all_products)} products across {page-1} pages")
        return all_products

    except Exception as e:
        print(f"❌ Comprehensive search failed: {e}")
        # Fallback para a pesquisa original se tudo falhar
        try:
            return scrape_tesco_search_cloudscraper(search_term)
        except:
            return []


def scrape_tesco_via_search(product_url: str, retailer_name: str) -> Dict[str, Any]:
    """
    Para Tesco, usar pesquisa em vez de página individual (que é bloqueada)
    """
    try:
        # Extrair ID do produto da URL
        product_id = product_url.split('/')[-1]
        print(f"🔄 Tesco individual page blocked, trying comprehensive search for ID: {product_id}")

        # Estratégia 1: Usar pesquisa abrangente cached
        try:
            print(f"🔍 Trying comprehensive search for product...")
            products = cached_tesco_search("paper tissue", max_products=100)  # Procurar em mais produtos
            for product in products:
                if product_id in product.get("url", ""):
                    if product.get("price") and product.get("title"):  # Validação rigorosa
                        print(f"✅ Found product via comprehensive search: {product.get('title')}")
                        product["scraping_method"] = "search_fallback_comprehensive"
                        product["original_url"] = product_url
                        product["status"] = "success"
                        return product
        except Exception as e:
            print(f"⚠️  Comprehensive search failed: {e}")

        # Estratégia 2: Pesquisas expandidas com throttling
        search_terms = [
            "toilet tissue", "tissue", "paper", "toilet paper", 
            "bathroom tissue", "soft tissue", "luxury tissue"
        ]

        for i, term in enumerate(search_terms):
            try:
                # Throttling para evitar bloqueios
                if i > 0:
                    time.sleep(3)  # Delay entre pesquisas

                print(f"🔍 Comprehensive searching for '{term}'...")
                products = cached_tesco_search(term, max_products=50)

                for product in products:
                    if product_id in product.get("url", ""):
                        # Validação rigorosa: deve ter preço E título
                        if product.get("price") and product.get("title"):
                            print(f"✅ Found via '{term}' search: {product.get('title')} - £{product.get('price')}")
                            product["scraping_method"] = f"search_fallback_{term}"
                            product["original_url"] = product_url
                            product["status"] = "success"
                            return product
                        else:
                            print(f"⚠️  Product found but missing price or title data")

            except Exception as e:
                print(f"⚠️  Search '{term}' failed: {e}")
                continue

        # Estratégia 3: Tentativa de pesquisa direta por ID (última tentativa)
        try:
            time.sleep(2)
            print(f"🔍 Last attempt: comprehensive search for product ID directly...")
            products = cached_tesco_search(product_id, max_products=30)

            for product in products:
                if product_id in product.get("url", "") and product.get("price") and product.get("title"):
                    print(f"✅ Found via ID search: {product.get('title')} - £{product.get('price')}")
                    product["scraping_method"] = "search_fallback_id"
                    product["original_url"] = product_url
                    product["status"] = "success"
                    return product
        except Exception as e:
            print(f"⚠️  ID search failed: {e}")

        # Se ainda não encontrou, retornar informação básica
        return {
            "url": product_url,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "retailer": retailer_name,
            "status": "partial_success",
            "scraping_method": "fallback_search_failed",
            "note": "Individual page blocked, search fallback did not find this specific product"
        }

    except Exception as e:
        return {
            "url": product_url,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "retailer": retailer_name,
            "status": "failed",
            "error": f"Search fallback failed: {str(e)}"
        }


def scrape_individual_product_page(url: str, retailer_name: str = "Unknown") -> Dict[str, Any]:
    """
    Faz scraping de uma página individual de produto
    """
    print(f"🔍 Scraping: {url}")

    try:
        # Abordagem especial para Tesco (usar pesquisa porque páginas individuais são bloqueadas)
        if "tesco.com" in url and "/products/" in url:
            return scrape_tesco_via_search(url, retailer_name)

        # Use cloudscraper para contornar proteções (outros sites)
        scraper = cloudscraper.create_scraper()
        ua = UserAgent()

        # Headers mais robustos
        scraper.headers.update({
            'User-Agent': ua.chrome,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-GB,en-US;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Cache-Control': 'max-age=0',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Sec-CH-UA': '"Google Chrome";v="120", "Chromium";v="120", "Not:A-Brand";v="99"',
            'Sec-CH-UA-Mobile': '?0',
            'Sec-CH-UA-Platform': '"Windows"',
        })

        # Múltiplas tentativas com diferentes estratégias
        strategies = [
            {'method': 'cloudscraper'},
            {'method': 'httpx_http2'},
            {'method': 'session_requests'},
            {'method': 'simple_requests'}
        ]

        for strategy in strategies:
            if strategy['method'] == 'cloudscraper':
                response = scraper.get(url, timeout=30)
            elif strategy['method'] == 'httpx_http2':
                try:
                    import httpx
                    with httpx.Client(http2=True, follow_redirects=True, timeout=30.0) as client:
                        response = client.get(url, headers=scraper.headers)
                except ImportError:
                    print(f"⚠️  httpx not installed, skipping HTTP/2 strategy")
                    continue
                except Exception as e:
                    print(f"⚠️  httpx HTTP/2 strategy error: {e}")
                    continue
            elif strategy['method'] == 'session_requests':
                session = requests.Session()
                session.headers.update(scraper.headers)
                response = session.get(url, timeout=30)
            else:  # simple_requests
                response = requests.get(url, headers=scraper.headers, timeout=30)

            if response.status_code == 200:
                break
            elif response.status_code == 403:
                print(f"⚠️  Estratégia {strategy['method']} bloqueada (403)")
                continue
            else:
                print(f"⚠️  Estratégia {strategy['method']} falhou ({response.status_code})")
                continue

        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')

            product_data = {
                "url": url,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "retailer": retailer_name,
                "scraping_method": "individual_page",
                "status": "success"
            }

            # Tentar encontrar título da página
            title_selectors = [
                # Tesco específico
                'h1._64Yvfa_title',
                'h1[data-testid*="title"]',
                # Genérico
                'h1',
                '.product-title',
                '.pdp-product-name',
                'title'
            ]

            for selector in title_selectors:
                if selector == 'title':
                    title_elem = soup.find('title')
                else:
                    title_elem = soup.select_one(selector)

                if title_elem:
                    title = title_elem.get_text(strip=True)
                    if title and len(title) > 3 and 'tesco' not in title.lower():
                        product_data["title"] = title
                        break

            # Tentar encontrar preço
            price_found = False

            # Seletores específicos para diferentes retalhistas
            price_selectors = [
                # Tesco
                '.price-current',
                '.price-value',
                '[data-testid*="price"]',
                # Genérico
                '.price',
                '.product-price',
                '.cost',
                '.pricing'
            ]

            for selector in price_selectors:
                price_elems = soup.select(selector)
                for price_elem in price_elems:
                    price_text = price_elem.get_text(strip=True)
                    if price_text and ('£' in price_text or '€' in price_text or '$' in price_text):
                        cur_sym, price = parse_price(price_text)
                        if price:
                            product_data["price"] = str(price)
                            product_data["currency"] = cur_sym or "£"
                            product_data["price_text"] = price_text
                            price_found = True
                            break
                if price_found:
                    break

            # Se não encontrou preço com seletores, procurar no texto
            if not price_found:
                all_text = soup.get_text()
                import re
                price_matches = re.findall(r'[£$€]\s*([0-9]+(?:\.[0-9]{2})?)', all_text)
                if price_matches:
                    try:
                        price_value = price_matches[0]
                        product_data["price"] = price_value
                        product_data["currency"] = "£"
                        product_data["price_text"] = f"£{price_value}"
                    except:
                        pass

            # Tentar encontrar descrição/detalhes
            desc_selectors = [
                '.product-description',
                '.product-details',
                '.pdp-description',
                '[data-testid*="description"]'
            ]

            for selector in desc_selectors:
                desc_elem = soup.select_one(selector)
                if desc_elem:
                    description = desc_elem.get_text(strip=True)
                    if description and len(description) > 10:
                        product_data["description"] = description[:500]  # Limitar tamanho
                        break

            return product_data

        else:
            print(f"❌ HTTP {response.status_code}")
            return {
                "url": url,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "retailer": retailer_name,
                "status": "failed",
                "error": f"HTTP {response.status_code}"
            }

    except Exception as e:
        print(f"❌ Erro: {e}")
        return {
            "url": url,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "retailer": retailer_name,
            "status": "failed",
            "error": str(e)
        }


def scrape_all_database_sites() -> Dict[str, Any]:
    """
    Faz scraping de todos os sites na base de dados
    """
    print("🚀 INICIANDO SCRAPING DE TODOS OS SITES DA BASE DE DADOS")
    print("=" * 60)

    # Buscar todos os SKUListings ativos
    active_listings = SKUListing.objects.filter(
        is_active=True, 
        retailer__is_active=True
    ).select_related('sku', 'retailer')

    if not active_listings:
        print("❌ Nenhum SKUListing ativo encontrado na base de dados!")
        return {"error": "No active listings found"}

    print(f"📋 Encontrados {active_listings.count()} SKUListings ativos")
    print()

    results = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_listings": active_listings.count(),
        "scraped_products": [],
        "failed_scrapes": [],
        "summary": {},
        "new_price_points": []
    }

    for i, listing in enumerate(active_listings, 1):
        print(f"📦 [{i}/{active_listings.count()}] {listing.sku.code} - {listing.sku.name}")
        print(f"🌐 {listing.retailer.name}: {listing.url}")

        # Fazer scraping da página
        scraped_data = scrape_individual_product_page(listing.url, listing.retailer.name)

        # VALIDAÇÃO RIGOROSA: só é sucesso se tem status="success" E dados essenciais
        is_valid_success = (
            scraped_data.get("status") == "success" and 
            scraped_data.get("title") and 
            scraped_data.get("price")
        )

        if is_valid_success:
            results["scraped_products"].append(scraped_data)

            # Salvar na base de dados (só com dados válidos)
            try:
                price = Decimal(scraped_data["price"])

                # Validação adicional: preço deve ser > 0
                if price <= 0:
                    raise ValueError(f"Invalid price: {price}")

                price_point = PricePoint.objects.create(
                    sku_listing=listing,
                    price=price,
                    raw_currency=scraped_data.get("currency", "£"),
                    raw_snapshot=json.dumps(scraped_data, ensure_ascii=False)
                )

                results["new_price_points"].append({
                    "sku_code": listing.sku.code,
                    "retailer": listing.retailer.name,
                    "price": str(price),
                    "timestamp": scraped_data["timestamp"]
                })

                print(f"✅ Sucesso! Preço: {scraped_data.get('price_text', 'N/A')}")

            except Exception as e:
                print(f"⚠️  Erro ao salvar na BD: {e}")
                # Se falhou a salvar, remover dos sucessos
                results["scraped_products"].pop()
                scraped_data["status"] = "failed"
                scraped_data["error"] = f"Database save failed: {str(e)}"
                results["failed_scrapes"].append(scraped_data)

        else:
            results["failed_scrapes"].append(scraped_data)
            print(f"❌ Falhou: {scraped_data.get('error', 'Unknown error')}")

        print("-" * 40)

        # Delay inteligente entre requests (mais longo para evitar bloqueios)
        if i < active_listings.count():  # Não fazer delay após o último produto
            delay = 5 if listing.retailer.name.lower() == "tesco" else 2
            print(f"⏳ Waiting {delay}s before next request...")
            time.sleep(delay)

    # Criar resumo
    results["summary"] = {
        "successful_scrapes": len(results["scraped_products"]),
        "failed_scrapes": len(results["failed_scrapes"]),
        "success_rate": f"{(len(results['scraped_products']) / active_listings.count() * 100):.1f}%",
        "new_price_points_created": len(results["new_price_points"])
    }

    return results


def save_scraping_report(results: Dict[str, Any], filename: str = "scraping_report.json"):
    """
    Salva o relatório de scraping
    """
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"📄 Relatório salvo em: {filename}")
        return True
    except Exception as e:
        print(f"❌ Erro ao salvar relatório: {e}")
        return False


def print_summary(results: Dict[str, Any]):
    """
    Imprime resumo dos resultados
    """
    print("\n" + "=" * 60)
    print("📊 RESUMO DO SCRAPING")
    print("=" * 60)

    summary = results.get("summary", {})

    print(f"🎯 Total de sites: {results.get('total_listings', 0)}")
    print(f"✅ Sucessos: {summary.get('successful_scrapes', 0)}")
    print(f"❌ Falhas: {summary.get('failed_scrapes', 0)}")
    print(f"📈 Taxa de sucesso: {summary.get('success_rate', '0%')}")
    print(f"💾 Novos price points: {summary.get('new_price_points_created', 0)}")

    if results.get("scraped_products"):
        print("\n🛒 PRODUTOS ENCONTRADOS:")
        for product in results["scraped_products"]:
            title = product.get("title", "Sem título")[:50]
            price = product.get("price_text", "Sem preço")
            print(f"  • {title} - {price}")

    if results.get("failed_scrapes"):
        print("\n⚠️  FALHAS:")
        for failure in results["failed_scrapes"]:
            error = failure.get("error", "Erro desconhecido")
            url = failure.get("url", "")[:50]
            print(f"  • {url} - {error}")


def main():
    """
    Função principal
    """
    print("🎯 SCRIPT DE SCRAPING DA BASE DE DADOS")
    print("Desenvolvido para Navigator Intelligence")
    print()

    try:
        # Executar scraping
        results = scrape_all_database_sites()

        # Imprimir resumo
        print_summary(results)

        # Salvar relatório
        report_filename = f"scraping_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        save_scraping_report(results, report_filename)

        print(f"\n🎉 Scraping concluído! Relatório: {report_filename}")

    except Exception as e:
        print(f"💥 Erro crítico: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
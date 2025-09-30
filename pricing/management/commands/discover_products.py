import re
import time
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.utils.text import slugify
from pricing.models import Retailer, RetailerSelector, SKU, SKUListing, PricePoint
from pricing.scraper import (
    scrape_tesco_search_cloudscraper,
    scrape_tesco_search_selenium,
    parse_price
)


class Command(BaseCommand):
    help = 'Discover and add Paper Tissue products from all configured retailers'

    def add_arguments(self, parser):
        parser.add_argument(
            '--search-term',
            type=str,
            default='paper tissue',
            help='Search term to use (default: "paper tissue")'
        )
        parser.add_argument(
            '--setup-retailers',
            action='store_true',
            help='Setup UK retailers before discovering products'
        )
        parser.add_argument(
            '--max-products',
            type=int,
            default=10,
            help='Maximum products to add per retailer (default: 10)'
        )

    def handle(self, *args, **options):
        search_term = options['search_term']
        setup_retailers = options['setup_retailers']
        max_products = options['max_products']

        self.stdout.write(self.style.SUCCESS(f'\n=== Product Discovery: "{search_term}" ===\n'))

        # Setup retailers if requested
        if setup_retailers:
            self.setup_uk_retailers()

        # Get all active retailers
        retailers = Retailer.objects.filter(is_active=True)
        
        if not retailers.exists():
            self.stdout.write(self.style.ERROR('No retailers found! Use --setup-retailers to create them.'))
            return

        total_added = 0
        total_scraped = 0

        for retailer in retailers:
            self.stdout.write(self.style.WARNING(f'\n--- Processing: {retailer.name} ---'))
            
            # Discover products for this retailer
            products = self.discover_products_for_retailer(retailer, search_term)
            
            if not products:
                self.stdout.write(self.style.WARNING(f'No products found for {retailer.name}'))
                continue

            # Add products to database
            added, scraped = self.add_products_to_database(retailer, products[:max_products])
            total_added += added
            total_scraped += scraped

        self.stdout.write(self.style.SUCCESS(f'\n=== Summary ==='))
        self.stdout.write(self.style.SUCCESS(f'Products added: {total_added}'))
        self.stdout.write(self.style.SUCCESS(f'Prices scraped: {total_scraped}'))

    def setup_uk_retailers(self):
        """Setup UK retailers with their selectors"""
        self.stdout.write('Setting up UK retailers...')
        
        retailers_config = [
            {
                'name': 'Tesco',
                'base_url': 'https://www.tesco.com',
                'selectors': {
                    'price_selector': '.price',
                    'promo_price_selector': '.offer-price',
                    'promo_text_selector': '.offer-text'
                }
            },
            {
                'name': 'Sainsbury\'s',
                'base_url': 'https://www.sainsburys.co.uk',
                'selectors': {
                    'price_selector': '.pd__cost__total',
                    'promo_price_selector': '.pd__cost__was',
                    'promo_text_selector': '.pd__cost__offer'
                }
            },
            {
                'name': 'Asda',
                'base_url': 'https://groceries.asda.com',
                'selectors': {
                    'price_selector': '.co-product__price',
                    'promo_price_selector': '.co-product__price--was',
                    'promo_text_selector': '.co-product__promo-text'
                }
            },
            {
                'name': 'Morrisons',
                'base_url': 'https://groceries.morrisons.com',
                'selectors': {
                    'price_selector': '.bop-price__current',
                    'promo_price_selector': '.bop-price__was',
                    'promo_text_selector': '.bop-offer-flag'
                }
            }
        ]

        for config in retailers_config:
            retailer, created = Retailer.objects.get_or_create(
                name=config['name'],
                defaults={'base_url': config['base_url'], 'is_active': True}
            )
            
            if created:
                self.stdout.write(self.style.SUCCESS(f'  ✓ Created retailer: {retailer.name}'))
            else:
                self.stdout.write(f'  - Retailer exists: {retailer.name}')

            # Create or update selectors
            selector, sel_created = RetailerSelector.objects.get_or_create(
                retailer=retailer,
                defaults=config['selectors']
            )
            
            if sel_created:
                self.stdout.write(f'    ✓ Created selectors for {retailer.name}')

    def discover_products_for_retailer(self, retailer, search_term):
        """Discover products for a specific retailer"""
        products = []
        
        if retailer.name == 'Tesco':
            # Try cloudscraper first, fallback to Selenium
            self.stdout.write('  Trying cloudscraper...')
            products = scrape_tesco_search_cloudscraper(search_term)
            
            if not products:
                self.stdout.write('  Cloudscraper failed, trying Selenium...')
                products = scrape_tesco_search_selenium(search_term)
            
            if products:
                self.stdout.write(self.style.SUCCESS(f'  ✓ Found {len(products)} products'))
            
        elif retailer.name in ["Sainsbury's", "Asda", "Morrisons"]:
            # For other retailers, use demo mode for now
            self.stdout.write(f'  Using demo mode for {retailer.name}')
            products = self.generate_demo_products(retailer, search_term)
        
        return products

    def generate_demo_products(self, retailer, search_term):
        """Generate demo products for retailers without scraping implementation"""
        demo_products = {
            "Sainsbury's": [
                {
                    "title": "Sainsbury's Soft & Strong Toilet Tissue 9 Pack",
                    "price": "4.50",
                    "currency": "£",
                    "url": f"{retailer.base_url}/products/toilet-tissue-9-pack"
                },
                {
                    "title": "Kleenex Tissues Ultra Soft 12 Box",
                    "price": "8.00",
                    "currency": "£",
                    "url": f"{retailer.base_url}/products/kleenex-tissues-12-box"
                }
            ],
            "Asda": [
                {
                    "title": "ASDA Shades Facial Tissues 80 Pack",
                    "price": "1.00",
                    "currency": "£",
                    "url": f"{retailer.base_url}/product/facial-tissues-80"
                },
                {
                    "title": "Regina Blitz Kitchen Roll 3 Pack",
                    "price": "3.50",
                    "currency": "£",
                    "url": f"{retailer.base_url}/product/kitchen-roll-3-pack"
                }
            ],
            "Morrisons": [
                {
                    "title": "Morrisons Toilet Tissue 16 Roll",
                    "price": "7.00",
                    "currency": "£",
                    "url": f"{retailer.base_url}/products/toilet-tissue-16-roll"
                },
                {
                    "title": "Andrex Gentle Clean Toilet Tissue 9 Roll",
                    "price": "6.50",
                    "currency": "£",
                    "url": f"{retailer.base_url}/products/andrex-gentle-clean-9"
                }
            ]
        }
        
        return demo_products.get(retailer.name, [])

    def add_products_to_database(self, retailer, products):
        """Add discovered products to database"""
        added_count = 0
        scraped_count = 0

        for product in products:
            try:
                title = product.get('title', '')
                url = product.get('url', '')
                price_str = product.get('price', '')
                currency = product.get('currency', '£')

                if not title or not url:
                    continue

                # Generate SKU code from title
                sku_code = self.generate_sku_code(retailer.name, title)

                # Create or get SKU
                sku, sku_created = SKU.objects.get_or_create(
                    code=sku_code,
                    defaults={'name': title}
                )

                if sku_created:
                    self.stdout.write(self.style.SUCCESS(f'  ✓ Created SKU: {sku_code} - {title}'))
                    added_count += 1
                else:
                    self.stdout.write(f'  - SKU exists: {sku_code}')

                # Create or get listing
                listing, listing_created = SKUListing.objects.get_or_create(
                    sku=sku,
                    retailer=retailer,
                    url=url,
                    defaults={'is_active': True}
                )

                if listing_created:
                    self.stdout.write(f'    ✓ Created listing for {retailer.name}')

                # Create price point if we have a price
                if price_str:
                    try:
                        # Use parse_price to handle currency symbols and formatting
                        cur_sym, price_decimal = parse_price(f"{currency}{price_str}")
                        
                        if price_decimal:
                            PricePoint.objects.create(
                                sku_listing=listing,
                                price=price_decimal,
                                raw_currency=cur_sym or currency,
                                raw_snapshot=f"Discovered: {title} @ {currency}{price_str}"
                            )
                            self.stdout.write(f'    ✓ Scraped price: {currency}{price_str}')
                            scraped_count += 1
                        else:
                            self.stdout.write(self.style.WARNING(f'    ! Could not parse price: {price_str}'))
                    except Exception as e:
                        self.stdout.write(self.style.WARNING(f'    ! Price error: {e}'))

            except Exception as e:
                self.stdout.write(self.style.ERROR(f'  Error adding product: {e}'))
                continue

        return added_count, scraped_count

    def generate_sku_code(self, retailer_name, product_title):
        """Generate a unique SKU code from retailer and product title"""
        # Clean the title
        clean_title = re.sub(r'[^\w\s-]', '', product_title.lower())
        words = clean_title.split()[:3]  # First 3 words
        
        # Create base code
        retailer_prefix = retailer_name[:4].upper().replace("'", "")
        title_part = '-'.join(words)[:20]  # Limit length
        
        base_code = f"{retailer_prefix}-{title_part}"
        
        # Make unique if needed
        code = base_code
        counter = 1
        while SKU.objects.filter(code=code).exists():
            code = f"{base_code}-{counter}"
            counter += 1
        
        return code

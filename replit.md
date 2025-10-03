# Overview

Navigator UK Market Intelligence is a Django-based web scraping platform designed for competitive price monitoring across UK retailers. The system allows users to configure CSS selectors for different retailers and automatically scrape product prices, building a historical database of pricing trends and promotional activities. The MVP includes a dashboard for viewing price data and manual scraping capabilities with full internationalization (PT/EN) and automated product discovery.

# Recent Changes (October 2025)

## Product Discovery System
- **Automated Discovery Command**: `discover_products` management command for automatic product finding
  - Searches retailers for specific terms (default: "paper tissue")
  - Auto-generates unique SKU codes from product titles
  - Creates SKUs, SKUListings, and PricePoints automatically
  - Real scraping for Tesco (24 products found), demo mode for Sainsbury's, Asda, Morrisons
  - Usage: `python manage.py discover_products --setup-retailers --max-products 5`
- **"Scrape Now" Button Behavior**: Updates prices for existing products ONLY (does not add new products)
  - Uses cloudscraper for better reliability against Cloudflare protection
  - Fallback to regex price extraction when CSS selectors fail
  - Clear feedback: shows retailer names that failed instead of just failure count
  - Selenium detection for blocked/error pages
- **Product Discovery**: Separate from "Scrape Now" - use `discover_products` command to add new products
  - Auto-discovers products from Tesco search pages (not individual pages)
  - Discovery and scraping are intentionally separate workflows

## Critical Bug Fixes
- **Price Parsing Regex**: Fixed `parse_price()` function that was removing decimal places
  - Changed `{{2}}` to `{2}` in regex pattern  
  - All prices now save correctly with decimals (£3.15 vs £3.00)
- **Template Dictionary Access**: Fixed home.html price display using `get_item` template tag
  - Prices display correctly in both English and Portuguese

## Selenium Fallback System (October 2025)
- **Automatic JavaScript Rendering**: 3-level fallback system for robust price extraction
  1. Cloudscraper with CSS selectors (fast, ~2-4s)
  2. Regex fallback on static HTML
  3. **Selenium with undetected-chromedriver** (JavaScript rendering, ~10-15s)
- **When Selenium Triggers**: Automatically when static HTML has no extractable prices
- **Benefits**:
  - Extracts prices from React/Next.js sites (Asda £1.35)
  - Bypasses advanced anti-bot protection (Tesco £1.55)
  - Saves fully rendered HTML (476-756KB) to JSON for analysis
- **Compatibility**: Fixed for Chromium 138 (removed incompatible options)

## JSON Export (October 2025)
- **Scraping Results Export**: All scraping data automatically saved to `extração.json`
  - **Format**: Dictionary with product names as keys (not array)
  - Includes: timestamp, retailer, product, URL, status, price, currency, error details
  - **Raw Information**: Full HTML source of each scraped page (null for failed scrapes)
  - Comprehensive summary: scraping_date, total_scraped, total_attempts
  - UTF-8 encoding with readable JSON formatting

## PDF Report Styling (October 2025)
- **Clean Print Layout**: CSS @media print rules + JavaScript for professional PDF generation
  - Hides all action buttons (Voltar/Back, Relatório/Report, Atualizar Dados/Update Data)
  - Keeps navigation bar (logo, title, language selector) visible in PDF
  - Keeps footer with developer link (www.marsshot.eu) visible in PDF
  - **Chart Resizing for Print**: JavaScript event listeners (`beforeprint`/`afterprint`)
    - Automatically increases chart height from 300px to 500px when printing
    - Calls `chartInstance.resize()` to re-render Chart.js canvas at correct size
    - Ensures all axis labels and data points appear in PDF
    - Restores original 300px height after printing
  - PDF contains: navigation bar, product info, full price chart (500px), historical data table, and footer

## Translation Updates (October 2025)
- **Portuguese Localization**: Updated "Scrape Now" button translation
  - Changed from "Extrair Agora" to "Recolher Dados" (more natural Portuguese)
  - Fixed duplicate msgid compilation errors in locale/pt/LC_MESSAGES/django.po
  - Clean compilation of .mo files for both PT and EN locales

## Multi-Retailer Configuration
- 4 UK retailers configured: Tesco, Sainsbury's, Asda, Morrisons
- Each with CSS selectors for price extraction
- Scraping uses cloudscraper + fallback regex for robust price extraction

### Retailer Status (October 2025)
**Success Rate: 3/4 (75%)**

- ✅ **Morrisons**: £3.60 - Works with cloudscraper (519KB HTML)
- ✅ **Tesco**: £1.55 - Selenium fallback when cloudscraper blocked (756KB rendered HTML)
  - CSS selector: `.ddsweb-price__container p.ddsweb-text`
  - CURRENCY_REGEX handles "Â£" encoding issue
- ✅ **Asda**: £1.35 - **Selenium extracts JavaScript-loaded prices** (477KB rendered HTML)
  - React/Next.js site requires JavaScript rendering
  - Automatic fallback to Selenium when static scraping fails
- ❌ **Sainsbury's**: 403 Forbidden (anti-bot blocks initial request)

# User Preferences

Preferred communication style: Simple, everyday language.

# System Architecture

## Web Framework
- **Django 5.0+** as the core web framework
- **SQLite** as the default database (Django's built-in)
- Standard Django project structure with apps pattern

## Data Models
The system uses a relational database design with five core models:
- **SKU**: Product identifiers and names
- **Retailer**: Store information and base URLs
- **RetailerSelector**: CSS selector configurations per retailer
- **SKUListing**: Links between SKUs and retailer product pages
- **PricePoint**: Historical price data with timestamps

This design allows for flexible retailer configuration without code changes.

## Scraping Engine
Multi-library approach for robust web scraping:
- **requests + BeautifulSoup**: Basic HTTP scraping
- **cloudscraper**: Anti-bot protection bypass
- **Selenium**: JavaScript-heavy sites
- **fake-useragent**: User agent rotation
- Configurable CSS selectors stored in database
- Support for regular prices, promotional prices, and promotional text extraction

## Frontend Architecture
- **Server-side rendered** Django templates
- **Pico CSS** framework for styling
- **Chart.js** for price trend visualization
- Responsive design with mobile support
- Print-friendly layouts

## Background Processing
- **Django management commands** for batch operations
- Synchronous scraping via web interface (MVP approach)
- Designed for future async task integration

## Admin Interface
- **Django Admin** for data management
- Custom admin views for all models
- Search and filtering capabilities
- Bulk operations support

# External Dependencies

## Web Scraping Libraries
- **requests**: HTTP client for API calls and basic scraping
- **beautifulsoup4**: HTML parsing and element extraction
- **lxml**: Fast XML/HTML parser backend
- **cloudscraper**: Cloudflare bypass capabilities
- **selenium**: Browser automation for JavaScript sites
- **playwright**: Modern browser automation alternative
- **requests-html**: JavaScript-enabled requests
- **fake-useragent**: User agent spoofing

## Frontend Libraries
- **Chart.js**: Data visualization and charting (CDN)
- **Pico CSS**: Lightweight CSS framework (CDN)

## Demo Data
- **Books to Scrape**: Test website for demonstration
- Includes sample retailer configurations and product data
- Pre-configured CSS selectors for immediate testing

## Potential Future Integrations
- **Celery/Redis**: For asynchronous task processing
- **PostgreSQL**: Production database upgrade
- **API endpoints**: For external integrations
- **Monitoring services**: For scraping reliability
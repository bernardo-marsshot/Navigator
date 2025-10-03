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
  - Clear feedback: shows failed retailers in HTML list format (not just count or comma-separated)
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
- **XSS Security**: Fixed HTML injection vulnerability in error messages (October 2025)
  - Retailer names now escaped with `escape()` before HTML list rendering
  - Prevents malicious database content from executing scripts

## Advanced Scraping System (October 2025)
- **4-Level Fallback Chain** for maximum reliability:
  1. **Cloudscraper** with persistent sessions & cookies (fast, ~2-4s)
     - Exponential backoff retry (3 attempts: 2s, 4s, 8s delays)
     - Per-retailer persistent scrapers maintain Cloudflare clearance
  2. **Regex + JSON extraction** on static HTML
     - JSON-LD structured data (`application/ld+json`)
     - React state parsing (`window.__PRELOADED_STATE__` for Sainsbury's)
  3. **httpx with HTTP/2** (modern protocol, shares cookies from step 1)
  4. **Selenium with undetected-chromedriver** (JavaScript rendering, ~10-15s)
- **Session Persistence**: Single scraper instance per retailer across requests
  - Reuses cookies to avoid repeated Cloudflare challenges
  - Significantly reduces 403 Forbidden errors
- **Cookie Sharing**: httpx inherits Cloudflare clearance from cloudscraper
- **Benefits**:
  - Extracts prices from React/Next.js sites (Asda £1.35)
  - Bypasses advanced anti-bot protection (Tesco £1.55)
  - Handles JSON-based pricing (Sainsbury's)
  - Saves fully rendered HTML (476-756KB) to JSON for analysis
- **Compatibility**: Fixed for Chromium 138 (removed incompatible options)

## JSON Export (October 2025)
- **Scraping Results Export**: All scraping data automatically saved to `extração.json`
  - **Format**: Dictionary with product names as keys (not array)
  - Includes: timestamp, retailer, product, URL, status, price, currency, error details
  - **Raw Information**: Full HTML source of each scraped page (null for failed scrapes)
  - Comprehensive summary: scraping_date, total_scraped, total_attempts
  - UTF-8 encoding with readable JSON formatting

## PDF Report System (October 2025)
- **Server-Generated PDFs**: Professional reports using WeasyPrint and matplotlib
  - **Two-page portrait layout**: Page 1 (chart with dates), Page 2 (price history table)
  - **Filename**: Just the SKU code (e.g., `106634562.pdf`)
  - **Visual Consistency**: Matplotlib styling matches website's Chart.js appearance
    - Light gray background (#f9fafb) and subtle grid lines
    - Soft color palette with #e5e7eb borders
    - Font styling matches web (gray text, medium-weight headers)
    - Clean, minimalist design aligned with Navigator branding
- **Data Deduplication**: Shows only most recent price point per day/hour/minute/retailer
  - Prevents duplicate points when multiple scrapes occur in same minute
  - Cleaner charts and tables with meaningful data only
- **Table Ordering**: Most recent data displayed first (descending timestamp)
  - Applies to both web pages and PDF reports
  - Consistent user experience across formats

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
**Target Success Rate: 4/4 (100%)** with new fallback improvements

- ✅ **Morrisons**: £3.60 - Works reliably with persistent cloudscraper (519KB HTML)
- ✅ **Tesco**: £1.55 - **Improved reliability** with persistent session + exponential backoff
  - CSS selector: `.ddsweb-price__container p.ddsweb-text`
  - CURRENCY_REGEX handles "Â£" encoding issue
  - 3-attempt retry with delays (2s, 4s, 8s) reduces 403 errors
  - Falls back to httpx/Selenium if needed
- ✅ **Asda**: £1.35 - **Selenium extracts JavaScript-loaded prices** (477KB rendered HTML)
  - React/Next.js site requires JavaScript rendering
  - Automatic fallback to Selenium when static scraping fails
- 🔄 **Sainsbury's**: **Improved with JSON extraction**
  - New `window.__PRELOADED_STATE__` parser extracts prices from React state
  - Falls back to JSON-LD structured data if needed
  - Should now extract prices even when CSS selectors fail

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
# Overview

Navigator UK Market Intelligence is a Django-based web scraping platform designed for competitive price monitoring across UK retailers. The system allows users to configure CSS selectors for different retailers and automatically scrape product prices, building a historical database of pricing trends and promotional activities. The MVP includes a dashboard for viewing price data and manual scraping capabilities with full internationalization (PT/EN) and automated product discovery.

# Recent Changes (September 2025)

## Product Discovery System
- **Automated Discovery Command**: `discover_products` management command for automatic product finding
  - Searches retailers for specific terms (default: "paper tissue")
  - Auto-generates unique SKU codes from product titles
  - Creates SKUs, SKUListings, and PricePoints automatically
  - Real scraping for Tesco (24 products found), demo mode for Sainsbury's, Asda, Morrisons
  - Usage: `python manage.py discover_products --setup-retailers --max-products 5`
- **Integrated with UI**: "Scrape Now" button now automatically discovers new products AND updates existing prices
  - Uses `discover_and_add_products()` function in scraper.py
  - Discovers up to 5 new products per retailer on each run
  - Seamlessly integrated into existing scraping workflow

## Critical Bug Fixes
- **Price Parsing Regex**: Fixed `parse_price()` function that was removing decimal places
  - Changed `{{2}}` to `{2}` in regex pattern  
  - All prices now save correctly with decimals (£3.15 vs £3.00)
- **Template Dictionary Access**: Fixed home.html price display using `get_item` template tag
  - Prices display correctly in both English and Portuguese

## Multi-Retailer Configuration
- 4 UK retailers configured: Tesco, Sainsbury's, Asda, Morrisons
- Each with CSS selectors for price extraction
- 11 products discovered across all retailers

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
# Overview

Navigator UK Market Intelligence is a Django-based web scraping platform designed for competitive price monitoring across UK retailers. The system allows users to configure CSS selectors for different retailers and automatically scrape product prices, building a historical database of pricing trends and promotional activities. The MVP includes a dashboard for viewing price data and manual scraping capabilities with full internationalization support (Portuguese/English).

# Recent Changes (September 2025)

## Scraping Functionality Implemented
- **Tesco Handler**: Custom scraping handler for Tesco products registered in RETAILER_HANDLER_REGISTRY
  - Hybrid approach: tries JSON-LD structured data → CSS selectors → demo fallback
  - Works with or without cloudscraper/fake-useragent dependencies
  - Demo mode with 3 real Tesco products (tissue products) for testing
- **Demo Data**: Created 3 SKUs and listings for demonstration (TESCO-001, TESCO-002, TESCO-003)
- **Template Fix**: Corrected home view to properly display latest prices for each SKU

## i18n System Fixes
- Fixed language toggle persistence using localStorage synchronized with server
- Resolved Chart.js rendering issues with Portuguese number format (comma decimals)
- Bootstrap script ensures language consistency between URL and displayed content

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
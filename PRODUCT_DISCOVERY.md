# Product Discovery Script

## Overview
The `discover_products` management command automatically discovers and adds Paper Tissue products from UK retailers to the database.

## Features
- **Multi-retailer support**: Tesco (real scraping), Sainsbury's, Asda, Morrisons (demo mode)
- **Automatic SKU creation**: Generates unique SKU codes from product titles
- **Automatic listing creation**: Links products to retailers with URLs
- **Price extraction**: Captures prices during discovery
- **Configurable**: Search term and max products can be customized

## Usage

### Basic Usage
```bash
python manage.py discover_products --setup-retailers
```

### Options

#### Setup Retailers First
```bash
python manage.py discover_products --setup-retailers
```
Creates UK retailers (Tesco, Sainsbury's, Asda, Morrisons) with CSS selectors.

#### Custom Search Term
```bash
python manage.py discover_products --search-term "kitchen roll"
```

#### Limit Products Per Retailer
```bash
python manage.py discover_products --max-products 5
```

#### Combined Example
```bash
python manage.py discover_products --setup-retailers --search-term "facial tissues" --max-products 3
```

## How It Works

### 1. Retailer Setup
When using `--setup-retailers`, the script creates:
- **Tesco**: Real scraping via cloudscraper/Selenium
- **Sainsbury's**: Demo mode with sample products
- **Asda**: Demo mode with sample products  
- **Morrisons**: Demo mode with sample products

Each retailer gets configured with CSS selectors for price extraction.

### 2. Product Discovery

#### For Tesco (Real Scraping)
1. Searches Tesco website using cloudscraper
2. Extracts product data from search results:
   - Product title
   - Price
   - Product URL
3. Falls back to Selenium if cloudscraper fails

#### For Other Retailers (Demo Mode)
Uses predefined demo products with realistic names and prices.

### 3. Database Population

For each discovered product:
1. **Generate SKU code**: `{RETAILER-PREFIX}-{title-keywords}`
   - Example: `TESC-tesco-luxury-soft`
2. **Create/Get SKU**: Adds product to SKU table
3. **Create Listing**: Links SKU to retailer with URL
4. **Create PricePoint**: Records the discovered price

## Output Example

```
=== Product Discovery: "paper tissue" ===

Setting up UK retailers...
  ✓ Created retailer: Tesco
    ✓ Created selectors for Tesco

--- Processing: Tesco ---
  Trying cloudscraper...
  ✓ Found 5 products
  ✓ Created SKU: TESC-tesco-luxury-soft - Tesco Luxury Soft White Toilet Tissue 6 Long Rolls
    ✓ Created listing for Tesco
    ✓ Scraped price: £3.15

=== Summary ===
Products added: 11
Prices scraped: 11
```

## Extending to More Retailers

To add real scraping for Sainsbury's, Asda, or Morrisons:

1. Create a scraping function similar to `scrape_tesco_search_cloudscraper()`
2. Update `discover_products_for_retailer()` method in the command
3. Add retailer-specific selectors

## SKU Code Generation

SKU codes are automatically generated using:
- First 4 letters of retailer name (uppercase)
- First 3 words of product title (cleaned)
- Auto-incrementing suffix if duplicate

Examples:
- `TESC-tesco-luxury-soft`
- `SAIN-sainsburys-soft-stro`
- `ASDA-asda-shades-facial`

## Notes

- **Tesco scraping is real** but may be blocked by anti-bot protections
- **Demo mode** provides realistic fallback data for testing
- **Price updates**: Run the script again to discover new products (existing products are skipped)
- **Use with caution**: Web scraping may violate retailer terms of service

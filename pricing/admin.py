
from django.contrib import admin
from .models import SKU, Retailer, RetailerSelector, SKUListing, PricePoint

@admin.register(SKU)
class SKUAdmin(admin.ModelAdmin):
    list_display = ("code", "name")
    search_fields = ("code", "name")

@admin.register(Retailer)
class RetailerAdmin(admin.ModelAdmin):
    list_display = ("name", "base_url", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)

@admin.register(RetailerSelector)
class RetailerSelectorAdmin(admin.ModelAdmin):
    list_display = ("retailer", "price_selector", "promo_price_selector", "promo_text_selector")

@admin.register(SKUListing)
class SKUListingAdmin(admin.ModelAdmin):
    list_display = ("sku", "retailer", "url", "is_active")
    list_filter = ("retailer", "is_active")
    search_fields = ("sku__code", "sku__name", "url")

@admin.register(PricePoint)
class PricePointAdmin(admin.ModelAdmin):
    list_display = ("sku_listing", "timestamp", "price", "promo_price", "promo_text", "raw_currency")
    list_filter = ("sku_listing__retailer",)
    search_fields = ("sku_listing__sku__code", "sku_listing__sku__name", "promo_text")

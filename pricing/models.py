
from django.db import models
from django.utils.translation import gettext_lazy as _

class SKU(models.Model):
    code = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=255)
    competitor_names = models.TextField(blank=True, help_text=_("Optional: other names this SKU might appear as."))
    def __str__(self):
        return f"{self.code} — {self.name}"

class Retailer(models.Model):
    name = models.CharField(max_length=100, unique=True)
    base_url = models.URLField(blank=True)
    is_active = models.BooleanField(default=True)
    def __str__(self):
        return self.name

class RetailerSelector(models.Model):
    retailer = models.OneToOneField(Retailer, on_delete=models.CASCADE, related_name="selectors")
    price_selector = models.CharField(max_length=255, help_text=_("CSS selector for current price (e.g., '.price_color')"))
    promo_price_selector = models.CharField(max_length=255, blank=True, help_text=_("CSS selector for promo price if any"))
    promo_text_selector = models.CharField(max_length=255, blank=True, help_text=_("CSS selector for promo text/badge"))
    def __str__(self):
        return f"Selectors for {self.retailer.name}"

class SKUListing(models.Model):
    sku = models.ForeignKey(SKU, on_delete=models.CASCADE, related_name="listings")
    retailer = models.ForeignKey(Retailer, on_delete=models.CASCADE, related_name="listings")
    url = models.URLField()
    is_active = models.BooleanField(default=True)
    class Meta:
        unique_together = ("sku", "retailer", "url")
    def __str__(self):
        return f"{self.sku.code} @ {self.retailer.name}"

class PricePoint(models.Model):
    sku_listing = models.ForeignKey(SKUListing, on_delete=models.CASCADE, related_name="price_points")
    timestamp = models.DateTimeField(auto_now_add=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    promo_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    promo_text = models.CharField(max_length=255, blank=True)
    raw_currency = models.CharField(max_length=10, blank=True)
    raw_snapshot = models.TextField(blank=True, help_text=_("Optional: raw extracted text for audit/debug"))
    class Meta:
        ordering = ["-timestamp"]
    def __str__(self):
        return f"{self.sku_listing} — {self.timestamp:%Y-%m-%d %H:%M}"

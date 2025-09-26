
from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse
from .models import SKU, PricePoint
from .scraper import run_scrape_for_all_active

def home(request):
    skus = SKU.objects.all().order_by("code")
    latest = {}
    for sku in skus:
        pp = PricePoint.objects.filter(sku_listing__sku=sku).order_by("-timestamp").first()
        latest[sku.id] = pp
    return render(request, "pricing/home.html", {"skus": skus, "latest": latest})

def sku_detail(request, pk):
    sku = get_object_or_404(SKU, pk=pk)
    price_points = PricePoint.objects.filter(sku_listing__sku=sku).select_related("sku_listing", "sku_listing__retailer").order_by("timestamp")
    return render(request, "pricing/sku_detail.html", {"sku": sku, "price_points": price_points})

def scrape_now(request):
    # Trigger scrape synchronously (simple MVP button)
    count = run_scrape_for_all_active()
    return redirect("home")

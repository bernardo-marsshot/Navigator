
from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods
from django.contrib import messages
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

@require_http_methods(["POST"])
@csrf_protect
def scrape_now(request):
    # Trigger scrape synchronously (simple MVP button)
    try:
        count = run_scrape_for_all_active()
        if count > 0:
            messages.success(request, f"Successfully scraped {count} listings!")
        else:
            messages.info(request, "No active listings found to scrape.")
    except Exception as e:
        messages.error(request, f"Error during scraping: {str(e)}")
    
    return redirect("home")

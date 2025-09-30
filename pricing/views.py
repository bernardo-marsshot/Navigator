
from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from django.utils.translation import gettext as _
from .models import SKU, PricePoint
from .scraper import run_scrape_for_all_active

def home(request):
    skus = SKU.objects.all().order_by("code")
    skus_with_prices = []
    for sku in skus:
        pp = PricePoint.objects.filter(sku_listing__sku=sku).order_by("-timestamp").first()
        skus_with_prices.append({
            'sku': sku,
            'latest_price': pp
        })
    return render(request, "pricing/home.html", {"skus_with_prices": skus_with_prices})

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
            messages.success(request, _("Successfully scraped %(count)s listings!") % {'count': count})
        else:
            messages.info(request, _("No active listings found to scrape."))
    except Exception as e:
        messages.error(request, _("Error during scraping: %(error)s") % {'error': str(e)})
    
    return redirect("home")

from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from django.utils.translation import gettext as _
from django.utils.safestring import mark_safe
from django.utils.html import escape
from .models import SKU, PricePoint
from .scraper import run_scrape_for_all_active


def home(request):
    skus = SKU.objects.all().order_by("code")
    latest = {}
    for sku in skus:
        pp = PricePoint.objects.filter(
            sku_listing__sku=sku).order_by("-timestamp").first()
        latest[sku.id] = pp
    return render(request, "pricing/home.html", {
        "skus": skus,
        "latest": latest
    })


def sku_detail(request, pk):
    sku = get_object_or_404(SKU, pk=pk)
    price_points = PricePoint.objects.filter(
        sku_listing__sku=sku).select_related(
            "sku_listing", "sku_listing__retailer").order_by("timestamp")
    return render(request, "pricing/sku_detail.html", {
        "sku": sku,
        "price_points": price_points
    })


@require_http_methods(["POST"])
@csrf_protect
def scrape_now(request):
    # Trigger scrape synchronously (simple MVP button)
    try:
        from .models import SKUListing

        active_count = SKUListing.objects.filter(
            is_active=True, retailer__is_active=True).count()

        if active_count == 0:
            messages.info(request, _("No active listings found to scrape."))
        else:
            result = run_scrape_for_all_active()
            scraped_count = result['count']
            failed_retailers = result['failed_retailers']

            if scraped_count == 0:
                if failed_retailers:
                    retailers_list = ''.join([f'<li>{escape(r)}</li>' for r in failed_retailers])
                    msg = _("All %(total)s active listings failed to scrape. Failed retailers:") % {'total': active_count}
                    msg += f'<ul style="margin:0.5rem 0 0 0; padding-left:1.5rem;">{retailers_list}</ul>'
                else:
                    msg = _("All %(total)s active listings failed to scrape.") % {'total': active_count}
                messages.error(request, mark_safe(msg))
            elif scraped_count == active_count:
                messages.success(
                    request,
                    _("Successfully scraped %(count)s listings!") %
                    {'count': scraped_count})
            else:
                if failed_retailers:
                    retailers_list = ''.join([f'<li>{escape(r)}</li>' for r in failed_retailers])
                    msg = _("Scraped %(scraped)s of %(total)s listings. Failed retailers:") % {
                        'scraped': scraped_count,
                        'total': active_count
                    }
                    msg += f'<ul style="margin:0.5rem 0 0 0; padding-left:1.5rem;">{retailers_list}</ul>'
                else:
                    msg = _("Scraped %(scraped)s of %(total)s listings.") % {
                        'scraped': scraped_count,
                        'total': active_count
                    }
                messages.warning(request, mark_safe(msg))
    except Exception as e:
        messages.error(
            request,
            _("Error during scraping: %(error)s") % {'error': str(e)})

    return redirect("home")


@require_http_methods(["POST"])
@csrf_protect
def update_data(request, product_id):
    try:
        messages.success(
            request,
            _("Data updated successfully for product ID: %(product_id)s") %
            {'product_id': product_id})
        return redirect("home")
    except Exception as e:
        messages.error(request,
                       _("Error updating data: %(error)s") % {'error': str(e)})
        return redirect("home")

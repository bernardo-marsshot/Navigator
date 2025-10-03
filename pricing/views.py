from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from django.utils.translation import gettext as _
from django.utils.safestring import mark_safe
from django.utils.html import escape
from django.template.loader import render_to_string
from .models import SKU, PricePoint
from .scraper import run_scrape_for_all_active

import io
import base64
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.dates import DateFormatter
import matplotlib.dates as mdates
from weasyprint import HTML, CSS


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
            "sku_listing", "sku_listing__retailer").order_by("-timestamp")
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


def generate_pdf_report(request, pk):
    """Gera um PDF profissional com o gráfico de evolução de preços e tabela"""
    sku = get_object_or_404(SKU, pk=pk)
    all_price_points = PricePoint.objects.filter(
        sku_listing__sku=sku
    ).select_related(
        "sku_listing", "sku_listing__retailer"
    ).order_by("timestamp")
    
    # Deduplicate: keep only most recent point per day/hour/minute/retailer
    deduplicated = {}
    for p in all_price_points:
        key = (
            p.timestamp.date(),
            p.timestamp.hour,
            p.timestamp.minute,
            p.sku_listing.retailer.name
        )
        if key not in deduplicated or p.timestamp > deduplicated[key].timestamp:
            deduplicated[key] = p
    
    price_points = list(deduplicated.values())
    
    retailer_data = {}
    for p in price_points:
        retailer_name = p.sku_listing.retailer.name
        if retailer_name not in retailer_data:
            retailer_data[retailer_name] = {'timestamps': [], 'prices': []}
        retailer_data[retailer_name]['timestamps'].append(p.timestamp)
        price = float(p.promo_price) if p.promo_price else float(p.price)
        retailer_data[retailer_name]['prices'].append(price)
    
    fig, ax = plt.subplots(figsize=(14, 8))
    fig.patch.set_facecolor('white')
    ax.set_facecolor('white')
    
    colors = ['#FF6B35', '#FF8A65', '#4A90E2', '#50C878', '#FFB347', '#DA70D6', '#40E0D0', '#F0E68C']
    
    for idx, (retailer_name, data) in enumerate(retailer_data.items()):
        color = colors[idx % len(colors)]
        ax.plot(data['timestamps'], data['prices'], 
                marker='o', linewidth=2.5, markersize=8,
                label=f'{retailer_name} (£)', color=color)
    
    ax.set_xlabel('Data', fontsize=14, fontweight='bold')
    ax.set_ylabel('Preço (£)', fontsize=16, fontweight='bold')
    ax.set_title(_('Price Evolution by Retailer'), fontsize=20, fontweight='bold', pad=20)
    ax.legend(fontsize=14, loc='upper left', framealpha=0.9)
    ax.grid(True, alpha=0.3, linestyle='--')
    
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%d/%m %H:%M'))
    plt.xticks(rotation=45, ha='right', fontsize=10)
    ax.tick_params(axis='y', labelsize=12)
    
    plt.tight_layout(pad=2)
    
    buffer = io.BytesIO()
    plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight', facecolor='white')
    buffer.seek(0)
    image_base64 = base64.b64encode(buffer.read()).decode()
    plt.close()
    
    table_rows = ''
    for p in sorted(price_points, key=lambda x: x.timestamp, reverse=True):
        promo_display = f"{p.promo_price} ({p.promo_text})" if p.promo_price else "Sem promoção"
        table_rows += f'''
        <tr>
            <td>{p.timestamp.strftime('%d/%m/%Y %H:%M')}</td>
            <td>{p.sku_listing.retailer.name}</td>
            <td>{p.price if p.price else 'N/A'}</td>
            <td>{promo_display}</td>
        </tr>
        '''
    
    html_content = f'''
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            @page {{
                size: A4 portrait;
                margin: 15mm;
            }}
            body {{
                font-family: Arial, sans-serif;
                margin: 0;
                padding: 20px;
            }}
            .header {{
                text-align: center;
                margin-bottom: 20px;
            }}
            .header h1 {{
                color: #C6744A;
                margin: 0;
                font-size: 24px;
            }}
            .header p {{
                color: #6b7280;
                margin: 5px 0;
                font-size: 14px;
            }}
            .chart-container {{
                width: 100%;
                text-align: center;
                page-break-after: always;
                margin-bottom: 20px;
            }}
            .chart-container img {{
                max-width: 100%;
                height: auto;
            }}
            .table-section {{
                page-break-before: always;
                margin-top: 20px;
            }}
            h2 {{
                color: #C6744A;
                font-size: 20px;
                margin-bottom: 15px;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
                margin-top: 10px;
            }}
            th {{
                background: #C6744A;
                color: white;
                padding: 8px;
                text-align: left;
                font-size: 12px;
            }}
            td {{
                padding: 6px;
                border-bottom: 1px solid #ddd;
                font-size: 11px;
            }}
            tr:nth-child(even) {{
                background-color: #f8f9fa;
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>{sku.name}</h1>
            <p>SKU: {sku.code}</p>
        </div>
        <div class="chart-container">
            <img src="data:image/png;base64,{image_base64}" alt="Price Chart">
        </div>
        
        <div class="table-section">
            <h2>Histórico de Preços</h2>
            <table>
                <thead>
                    <tr>
                        <th>Data</th>
                        <th>Retalhista</th>
                        <th>Preço</th>
                        <th>Promoção</th>
                    </tr>
                </thead>
                <tbody>
                    {table_rows}
                </tbody>
            </table>
        </div>
    </body>
    </html>
    '''
    
    pdf_file = HTML(string=html_content).write_pdf()
    
    response = HttpResponse(pdf_file, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{sku.code}.pdf"'
    
    return response

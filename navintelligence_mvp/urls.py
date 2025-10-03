from django.contrib import admin
from django.urls import path, include
from django.conf.urls.i18n import i18n_patterns
from pricing import views

# Non-translated URLs (API endpoints, admin, etc.)
urlpatterns = [
    path("admin/", admin.site.urls),
    path("i18n/", include('django.conf.urls.i18n')),  # Language selector
]

# Translated URLs
urlpatterns += i18n_patterns(
    path("", views.home, name="home"),
    path("sku/<int:pk>/", views.sku_detail, name="sku_detail"),
    path("sku/<int:pk>/pdf/", views.generate_pdf_report, name="pdf_report"),
    path("scrape-now/", views.scrape_now, name="scrape_now"),
    prefix_default_language=True,  # Don't add /pt/ for default language
)

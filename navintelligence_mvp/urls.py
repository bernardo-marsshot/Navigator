
from django.contrib import admin
from django.urls import path
from pricing import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", views.home, name="home"),
    path("sku/<int:pk>/", views.sku_detail, name="sku_detail"),
    path("scrape-now/", views.scrape_now, name="scrape_now"),
]

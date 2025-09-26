
from django.core.management.base import BaseCommand
from pricing.scraper import run_scrape_for_all_active

class Command(BaseCommand):
    help = "Scrape prices for all active SKU listings"

    def handle(self, *args, **options):
        count = run_scrape_for_all_active()
        self.stdout.write(self.style.SUCCESS(f"Created {count} price points."))

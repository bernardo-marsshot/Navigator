# pricing/management/commands/scrape_all.py
from django.core.management.base import BaseCommand
from pricing.scraper import run_scrape_for_all_active


class Command(BaseCommand):
    help = "Scrape all active SKU listings for all active retailers and create PricePoints"

    def add_arguments(self, parser):
        parser.add_argument("--min-delay",
                            type=float,
                            default=0.8,
                            help="Minimum delay between requests")
        parser.add_argument("--max-delay",
                            type=float,
                            default=1.8,
                            help="Maximum delay between requests")

    def handle(self, *args, **opts):
        count = run_scrape_for_all_active(rate_limit=(opts["min_delay"],
                                                      opts["max_delay"]))
        self.stdout.write(
            self.style.SUCCESS(f"Created {count} PricePoint(s)."))

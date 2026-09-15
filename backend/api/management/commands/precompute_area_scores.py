"""precompute_area_scores — warm the per-area institution geo-mean cache.

Run this immediately after ``clear_rankings_cache`` following every data
pipeline re-ingest so the first filtered request (``?area=<code>``) does not
incur a cold-cache DB scan.

Usage::

    python manage.py precompute_area_scores

The command iterates every ``ResearchArea`` that is actually referenced by at
least one ``Conference``, calls ``_compute_area_institution_geo_means`` for each
code (which writes to cache), and reports the wall-clock time taken.

Exit 0 on success, 1 if any area fails.
"""

import time

from django.core.management.base import BaseCommand

from api.models import Conference, ResearchArea
from api.views import _compute_area_institution_geo_means, CACHE_KEY_AREA_GEO_PREFIX


class Command(BaseCommand):
    help = (
        "Pre-warm the per-area institution geo-mean cache for every active "
        "research area.  Run after clear_rankings_cache + pipeline re-ingest."
    )

    def handle(self, *args, **options):
        # Only areas that actually have conferences — identical gate used in AreasView.
        codes_in_use = (
            Conference.objects.filter(area__isnull=False)
            .values_list("area", flat=True)
            .distinct()
        )
        areas = list(
            ResearchArea.objects.filter(code__in=codes_in_use).order_by("code")
        )

        if not areas:
            self.stdout.write(self.style.WARNING("  No active research areas found.  Nothing to precompute."))
            return

        self.stdout.write(f"  Precomputing geo-mean scores for {len(areas)} research area(s)...")

        errors = []
        t0 = time.monotonic()

        for area in areas:
            cache_key = CACHE_KEY_AREA_GEO_PREFIX + area.code
            try:
                result = _compute_area_institution_geo_means(area.code)
                self.stdout.write(
                    f"  [{area.code}] {area.name}: "
                    f"{len(result)} institution(s) scored  ->  {cache_key}"
                )
            except Exception as exc:  # noqa: BLE001
                msg = f"  [{area.code}] {area.name}: FAILED - {exc}"
                self.stderr.write(self.style.ERROR(msg))
                errors.append(msg)

        elapsed = time.monotonic() - t0

        if errors:
            for err in errors:
                self.stderr.write(self.style.ERROR(err))
            raise SystemExit(1)

        self.stdout.write(
            self.style.SUCCESS(
                f"  Done. {len(areas)} area(s) cached in {elapsed:.2f}s.  "
                f"Next filtered requests will be served from cache."
            )
        )

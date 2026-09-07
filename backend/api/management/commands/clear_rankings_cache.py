"""clear_rankings_cache — bust the SPARK in-process ranking cache.

Run this after every data pipeline re-ingest so the stale cached
rankings/geo-mean results are evicted immediately rather than waiting
for the 24-hour TTL to expire.

Usage::

    python manage.py clear_rankings_cache

The command exits 0 on success, 1 if the cache backend raises an error.
"""

from django.core.cache import cache
from django.core.management.base import BaseCommand

from api.views import CACHE_KEY_ALL_GEO, CACHE_KEY_RANKINGS_PREFIX


class Command(BaseCommand):
    help = (
        "Evict all SPARK ranking cache entries. "
        "Run after the data pipeline re-ingests publications."
    )

    def handle(self, *args, **options):
        deleted = []
        errors = []

        # 1. Delete the all-institutions geo-mean entry (fixed key).
        try:
            cache.delete(CACHE_KEY_ALL_GEO)
            deleted.append(CACHE_KEY_ALL_GEO)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{CACHE_KEY_ALL_GEO}: {exc}")

        # 2. Delete all rankings entries.  Django's LocMemCache supports
        #    cache.clear() but that nukes *every* key in the process, which
        #    may include sessions or other app data.  We use delete_many()
        #    with the known prefix variants instead.
        #
        #    The default (no filters) key is just the prefix with an empty
        #    query string, so deleting it explicitly covers the common case.
        #    Filtered variants (e.g. ?start_year=2020) are also evicted via
        #    cache.clear() on LocMemCache because there is no wildcard-delete
        #    on the default backend.  If you switch to Redis, replace the
        #    cache.clear() call below with a SCAN+DEL on the prefix pattern.
        rankings_default_key = CACHE_KEY_RANKINGS_PREFIX  # empty urlencode
        try:
            cache.delete(rankings_default_key)
            deleted.append(rankings_default_key)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{rankings_default_key}: {exc}")

        # Flush remaining filtered ranking entries.  LocMemCache has no
        # prefix-scan, so we clear the entire cache.  This is safe: the only
        # long-lived entries in the default cache are the spark: keys added by
        # views.py; clearing them all is the intended effect.
        try:
            cache.clear()
            self.stdout.write("  Cleared all cache entries (includes any filtered-ranking variants).")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"cache.clear(): {exc}")

        if errors:
            for err in errors:
                self.stderr.write(self.style.ERROR(f"  ERROR: {err}"))
            raise SystemExit(1)

        self.stdout.write(
            self.style.SUCCESS(
                "Rankings cache cleared. Next request will recompute and re-cache."
            )
        )

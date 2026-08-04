"""Capture every API response against the *real* database, for before/after diffing.

The contract tests in api/tests/ prove the response shape is stable for a small
hand-built dataset. This script is the other half: it proves the response
*bytes* are stable for the actual production data, which is what the frontend
consumes. Run it before a schema change and after, then diff the two trees:

    python tools/api_snapshot.py /tmp/before
    ... apply migrations ...
    python tools/api_snapshot.py /tmp/after
    diff -ru /tmp/before /tmp/after && echo "API unchanged"

Responses are written one file per request, pretty-printed with sorted keys so
the diff is line-oriented and readable.
"""

import json
import os
import sys

# The test client sends Host: testserver, which the hardened ALLOWED_HOSTS in
# settings.py does not include. Widen it for this process only.
os.environ.setdefault('DJANGO_ALLOWED_HOSTS', 'testserver,localhost,127.0.0.1')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django  # noqa: E402

django.setup()

from django.test import Client  # noqa: E402

from api.models import Faculty, Institution  # noqa: E402


def build_urls():
    """Every endpoint, plus the filter combinations the frontend actually sends."""
    urls = [
        '/api/',
        '/api/stats/',
        '/api/areas/',
        '/api/conferences/',
        '/api/rankings/',
        '/api/rankings/?area=4602',
        '/api/rankings/?area=4602,4611',
        '/api/rankings/?start_year=2020',
        '/api/rankings/?end_year=2022',
        '/api/rankings/?start_year=2018&end_year=2024&area=4613',
        '/api/institutions/',
        '/api/institutions/?search=iit',
        '/api/institutions/?search=zzz-no-match',
        '/api/publications/',
        '/api/faculty/',
        '/api/faculty/?search=a',
        '/api/faculty/?start_year=2020&area=4602',
        # Malformed input must keep returning 400, not 500.
        '/api/rankings/?start_year=abc',
        '/api/rankings/?start_year=1500',
        '/api/publications/?institution=notanint',
        '/api/institutions/999999/',
        '/api/faculty/999999/',
    ]

    for pk in Institution.objects.values_list('id', flat=True).order_by('id'):
        urls.append(f'/api/institutions/{pk}/')
        urls.append(f'/api/institutions/{pk}/trends/')
        urls.append(f'/api/publications/?institution={pk}')

    # Faculty detail for a deterministic spread: the 20 with the most authorships
    # (exercises the scoring paths) plus the 5 with none (exercises the empty case).
    from django.db.models import Count

    ranked = Faculty.objects.annotate(n=Count('authorships')).order_by('-n', 'id')
    for fac in list(ranked[:20]) + list(ranked.reverse()[:5]):
        urls.append(f'/api/faculty/{fac.id}/')

    return sorted(set(urls))


def slugify_url(url):
    return url.replace('/', '_').replace('?', '__').replace('&', '_').replace('=', '-').strip('_')


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)

    out_dir = sys.argv[1]
    os.makedirs(out_dir, exist_ok=True)

    client = Client()
    index = []

    for url in build_urls():
        resp = client.get(url)
        try:
            body = json.loads(resp.content)
        except ValueError:
            body = {'_non_json_body': resp.content.decode('utf-8', 'replace')}

        record = {'url': url, 'status': resp.status_code, 'body': body}
        path = os.path.join(out_dir, slugify_url(url) + '.json')
        with open(path, 'w') as fh:
            json.dump(record, fh, indent=2, sort_keys=True)
            fh.write('\n')
        index.append({'url': url, 'status': resp.status_code, 'bytes': len(resp.content)})
        print(f'{resp.status_code}  {url}')

    with open(os.path.join(out_dir, '_index.json'), 'w') as fh:
        json.dump(index, fh, indent=2, sort_keys=True)
        fh.write('\n')

    print(f'\n{len(index)} responses written to {out_dir}')


if __name__ == '__main__':
    main()

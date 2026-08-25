#!/bin/sh
set -e

echo "[*] Applying database migrations..."
python manage.py migrate --noinput

echo "[*] Collecting static files..."
python manage.py collectstatic --noinput

echo "[*] Loading seed data (institutions, departments, conferences)..."
python manage.py load_seed_data

echo "[*] Loading pre-scraped rankings data..."
python manage.py load_rankings

echo "[*] Starting Gunicorn WSGI server on port 8001..."
exec gunicorn --workers 3 --bind 0.0.0.0:8001 backend.wsgi:application

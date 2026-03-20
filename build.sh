#!/usr/bin/env bash
set -o errexit

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

# Keep a single static artifact directory to avoid ambiguity with the legacy `staticfiles/` name.
rm -rf staticfiles .staticfiles
python manage.py collectstatic --noinput

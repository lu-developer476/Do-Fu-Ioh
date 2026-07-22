#!/usr/bin/env bash
set -o errexit
set -o pipefail

has_lfs_pointer_assets() {
  python - <<'PY'
from pathlib import Path

roots = [Path('public/images')]
for root in roots:
    if not root.exists():
        continue
    for path in root.rglob('*'):
        if path.is_file() and path.suffix.lower() in {'.png', '.jpg', '.jpeg', '.webp'}:
            with path.open('rb') as fh:
                if fh.read(42) == b'version https://git-lfs.github.com/spec':
                    raise SystemExit(0)
raise SystemExit(1)
PY
}

ensure_lfs_assets() {
  if ! has_lfs_pointer_assets; then
    return
  fi

  if ! command -v git >/dev/null 2>&1 || ! command -v git-lfs >/dev/null 2>&1; then
    echo "ERROR: Las imágenes en public/images son punteros de Git LFS." >&2
    echo "Instalá Git LFS y ejecutá 'git lfs pull' antes del build/deploy." >&2
    exit 1
  fi

  git lfs install --local
  git lfs pull

  if has_lfs_pointer_assets; then
    echo "ERROR: Git LFS no descargó las imágenes reales; todavía quedan punteros en public/images." >&2
    echo "Verificá que el remoto tenga objetos LFS y que Render/GitLab tenga acceso a ellos." >&2
    exit 1
  fi
}

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
ensure_lfs_assets

# Keep a single static artifact directory to avoid ambiguity with the legacy `staticfiles/` name.
rm -rf staticfiles .staticfiles
python manage.py collectstatic --noinput

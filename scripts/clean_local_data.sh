#!/usr/bin/env bash
# Cleans up any locally generated scrape data and HTML builds,
# ensuring the local repository keeps only source code.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

echo "🧹 Cleaning local generated data and build artifacts..."

# 1. Re-apply sparse checkout to ensure tracked data files are not checked out
if git config --get core.sparsecheckout >/dev/null 2>&1; then
  git sparse-checkout reapply || true
fi

# 2. Remove local untracked data and generated HTML files
rm -rf data/ site/ hotel-charts/ data_runs/ storage/*.csv
rm -f index_filter_*.html hotels.html hotels_catalog_data.json hotel_aliases_review.json price_alerts_history.json
rm -f *.db *.db-shm *.db-wal *.sqlite *.sqlite3

# 3. Clean python bytecode caches
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -type f -name "*.pyc" -delete 2>/dev/null || true

echo "✅ Cleaned! Only source code remains."
du -sh "$REPO_DIR"


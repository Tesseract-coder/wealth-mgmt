#!/usr/bin/env bash
# Screenshot every page in light and dark at desktop and phone width with headless Chrome.
# Usage: scripts/screenshots.sh <out-dir> [base-url]   (the app must be running: make dev)
set -euo pipefail
OUT=${1:?out dir}
BASE=${2:-http://localhost:5173}
CHROME=${CHROME:-google-chrome}
mkdir -p "$OUT"

PAGES=(
  "overview|/"
  "holdings|/holdings"
  "analysis|/analysis"
  "stock-signal|/analysis/RELIANCE.NS"
  "stock-technical|/analysis/RELIANCE.NS?view=technical"
  "stock-fundamental|/analysis/RELIANCE.NS?view=fundamental"
  "stock-backtest|/analysis/RELIANCE.NS?view=backtest"
  "mutual-funds|/mutual-funds"
  "fund-detail|/mutual-funds/122639"
  "screener|/screener"
  "watchlist|/watchlist"
  "compare|/compare?t=RELIANCE.NS,TCS.NS,INFY.NS"
  "import|/import"
  "settings|/settings"
  "onboarding|/onboarding"
  "components|/dev/components"
)
WIDTHS=("desktop|1440,2400" "phone|390,2400")

for page in "${PAGES[@]}"; do
  name=${page%%|*}; path=${page#*|}
  for w in "${WIDTHS[@]}"; do
    wname=${w%%|*}; size=${w#*|}
    for theme in light dark; do
      # ?theme= previews a theme without saving it (useTheme). Pages before the redesign followed the
      # system setting instead, so also pass the matching colour-scheme flag.
      flags=(--blink-settings=preferredColorScheme=$([ "$theme" = dark ] && echo 0 || echo 1))
      [ "$theme" = dark ] && flags+=(--force-dark-mode)
      sep=$([[ "$path" == *\?* ]] && echo "&" || echo "?")
      profile=$(mktemp -d)  # fresh profile: no saved theme in localStorage
      "$CHROME" --headless=new --disable-gpu --hide-scrollbars --user-data-dir="$profile" \
        "${flags[@]}" --window-size="$size" --virtual-time-budget=20000 \
        --screenshot="$OUT/$name-$wname-$theme.png" "$BASE$path${sep}theme=$theme" >/dev/null 2>&1 || echo "failed: $name $wname $theme"
      rm -rf "$profile"
    done
  done
done
echo "Saved to $OUT"

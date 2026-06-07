#!/bin/bash
# Encode small batches and push to server continuously.
# Ctrl+C to stop cleanly.

OUT_H="/tmp/broadcast_encode/horizontal"
OUT_V="/tmp/broadcast_encode/vertical"
SERVER="root@138.201.21.95"
BATCH=0

mkdir -p "$OUT_H" "$OUT_V"

# Source drives
SOURCES=(
  "/Volumes/luke"
  "/Volumes/padme"
  "/Volumes/yoda"
)

echo "=== encode_and_push — small batch mode ==="
echo "Ctrl+C to stop"
echo ""

while true; do
  BATCH=$((BATCH + 1))
  echo "────────────────────────────────────────"
  echo "Batch $BATCH — $(date '+%H:%M:%S')"
  echo ""

  # Encode 1 clip per source file, all drives, horizontal
  for SRC in "${SOURCES[@]}"; do
    [ -d "$SRC" ] || continue
    LABEL=$(basename "$SRC")
    echo "[H] $LABEL..."
    python3 /Users/gab/Desktop/gab-ae/footage/batch_encode.py \
      --base "$SRC" --prefix "$LABEL" \
      --clips 1 --min 12 --max 15 \
      --out "$OUT_H" --no-push 2>&1 | grep -E "✓|✗|encoded|Error"
  done

  # Encode 1 clip per source file, vertical-friendly drives
  for SRC in "/Volumes/yoda" "/Volumes/padme"; do
    [ -d "$SRC" ] || continue
    LABEL=$(basename "$SRC")-v
    echo "[V] $LABEL..."
    python3 /Users/gab/Desktop/gab-ae/footage/batch_encode.py \
      --base "$SRC" --prefix "$LABEL" \
      --clips 1 --min 12 --max 15 \
      --out "$OUT_V" --no-push --vertical 2>&1 | grep -E "✓|✗|encoded|Error"
  done

  # Count new clips
  H_NEW=$(find "$OUT_H" -name "*.mp4" ! -name "*.wip.mp4" | wc -l | tr -d ' ')
  V_NEW=$(find "$OUT_V" -name "*.mp4" ! -name "*.wip.mp4" | wc -l | tr -d ' ')
  echo ""
  echo "Clips ready — horizontal: $H_NEW  vertical: $V_NEW"

  # Push horizontal
  if [ "$H_NEW" -gt 0 ]; then
    echo "Pushing horizontal → server..."
    rsync -a --exclude '*.wip.mp4' "$OUT_H/" "$SERVER:/opt/broadcast/"
    ssh "$SERVER" "systemctl restart musique" && echo "✓ horizontal loop updated"
    rm -f "$OUT_H"/*.mp4
  fi

  # Push vertical
  if [ "$V_NEW" -gt 0 ]; then
    echo "Pushing vertical → server..."
    rsync -a --exclude '*.wip.mp4' "$OUT_V/" "$SERVER:/opt/broadcast_vertical/"
    ssh "$SERVER" "systemctl restart musique_vertical" && echo "✓ vertical loop updated"
    rm -f "$OUT_V"/*.mp4
  fi

  echo ""
  echo "Batch $BATCH done. Starting next..."
  echo ""
done

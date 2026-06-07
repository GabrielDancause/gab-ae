#!/bin/bash
# Upload Meta glasses session (May 29-30 2026) to Internet Archive as private backup

IA_ID="gab-raw-meta-glasses-2026-05-29"
SRC="/Volumes/obiwan/2026-06-05 - export from iPhone"
TITLE="Meta Glasses Session — May 29–30, 2026 (raw)"
DESC="Raw footage and photos from Meta Ray-Ban glasses, May 29–30 2026. Private backup by Gab Dancause."
IA_PATH=":internetarchive,access_key_id=${IA_ACCESS:-Ot0FVHkLiDTD4WDE},secret_access_key=${IA_SECRET:-caXpcbAZF8nfBX1D}:${IA_ID}"

FILES=(
  "video-31830_singular_display.MOV"
  "video-31835_singular_display.MOV"
  "video-31842_singular_display.MOV"
  "video-31848_singular_display.MOV"
  "video-31855_singular_display.MOV"
  "video-31862_singular_display.MOV"
  "video-31867_singular_display.MOV"
  "video-31872_singular_display.MOV"
  "video-31877_singular_display.MOV"
  "video-31974_singular_display.MOV"
  "video-31979_singular_display.MOV"
  "video-31984_singular_display.MOV"
  "video-31989_singular_display.MOV"
  "od_photo-31775_singular_display_fullPicture.HEIC"
  "photo-31827_singular_display_fullPicture.HEIC"
  "photo-31890_singular_display_fullPicture.HEIC"
  "photo-31962_singular_display_fullPicture.HEIC"
  "photo-31968_singular_display_fullPicture.HEIC"
)

echo "=== Uploading Meta glasses session to IA: ${IA_ID} ==="
echo "Files: ${#FILES[@]}"
echo ""

OK=0
FAIL=0

for f in "${FILES[@]}"; do
  fp="${SRC}/${f}"
  if [ ! -f "$fp" ]; then
    echo "MISSING: $f"
    ((FAIL++))
    continue
  fi
  echo "[upload] $f"
  rclone copyto "$fp" "${IA_PATH}/${f}" \
    --progress \
    --header-upload "x-archive-meta-title:${TITLE}" \
    --header-upload "x-archive-meta-description:${DESC}" \
    --header-upload "x-archive-meta-mediatype:movies" \
    --header-upload "x-archive-meta-subject:gab;meta-glasses;raw;backup" \
    --header-upload "x-archive-meta-creator:Gab Dancause" \
    --header-upload "x-archive-meta-noindex:true" \
    --header-upload "x-archive-meta-access-control:private" \
    2>&1
  if [ $? -eq 0 ]; then
    echo "  ✓ $f"
    ((OK++))
  else
    echo "  ✗ FAILED: $f"
    ((FAIL++))
  fi
done

echo ""
echo "=== Done: ${OK} uploaded, ${FAIL} failed ==="
echo "IA item: https://archive.org/details/${IA_ID}"

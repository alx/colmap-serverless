#!/bin/bash
# vastai_entrypoint.sh
# Reads job parameters from environment variables set by the Vast.ai template,
# runs the COLMAP pipeline, and prints the result.

set -euo pipefail

VIDEO_URL="${VIDEO_URL:-}"
VIDEO_URLS="${VIDEO_URLS:-}"   # comma-separated list
NUM_FRAMES="${NUM_FRAMES:-150}"
MATCHING="${MATCHING:-sequential}"
CAMERA_MODEL="${CAMERA_MODEL:-SIMPLE_RADIAL}"
SEQUENTIAL_OVERLAP="${SEQUENTIAL_OVERLAP:-10}"
GPU="${GPU:-true}"
QUALITY="${QUALITY:-high}"

if [ -z "$VIDEO_URL" ] && [ -z "$VIDEO_URLS" ]; then
  echo "ERROR: Set VIDEO_URL or VIDEO_URLS environment variable before launching."
  exit 1
fi

# Build the Python input payload
if [ -n "$VIDEO_URLS" ]; then
  # Convert comma-separated list to JSON array
  URLS_JSON=$(python3 -c "
import json, sys
urls = [u.strip() for u in '${VIDEO_URLS}'.split(',')]
print(json.dumps(urls))
")
  INPUT_JSON=$(python3 -c "
import json
inp = {
  'video_urls': ${URLS_JSON},
  'num_frames': int('${NUM_FRAMES}'),
  'matching': '${MATCHING}',
  'camera_model': '${CAMERA_MODEL}',
  'sequential_overlap': int('${SEQUENTIAL_OVERLAP}'),
  'gpu': '${GPU}' == 'true',
  'quality': '${QUALITY}',
}
print(json.dumps({'input': inp}))
")
else
  INPUT_JSON=$(python3 -c "
import json
inp = {
  'video_url': '${VIDEO_URL}',
  'num_frames': int('${NUM_FRAMES}'),
  'matching': '${MATCHING}',
  'camera_model': '${CAMERA_MODEL}',
  'sequential_overlap': int('${SEQUENTIAL_OVERLAP}'),
  'gpu': '${GPU}' == 'true',
  'quality': '${QUALITY}',
}
print(json.dumps({'input': inp}))
")
fi

echo "=== Starting COLMAP pipeline ==="
echo "Input: $INPUT_JSON"

python3 /app/handler.py --test_input "$INPUT_JSON"

#!/usr/bin/env bash
set -euo pipefail

IMAGE="colmap-serverless:local-test"
VIDEO_URL="https://github.com/alx/runsplat/releases/download/v0.1.5/lighthouse.mp4"
NUM_FRAMES=30     # low count so the test finishes quickly
TIMEOUT=900       # COLMAP build is slow; allow 15 min

# ── flags ──────────────────────────────────────────────────────────────────────
NO_BUILD=0
for arg in "$@"; do
  case $arg in
    --no-build) NO_BUILD=1 ;;
    *) echo "Usage: $0 [--no-build]"; exit 1 ;;
  esac
done

# ── helpers ────────────────────────────────────────────────────────────────────
pass() { echo "[PASS] $*"; }
fail() { echo "[FAIL] $*"; exit 1; }

# ── GPU check ─────────────────────────────────────────────────────────────────
if ! docker info 2>/dev/null | grep -q "nvidia"; then
  echo "WARNING: nvidia runtime not listed in 'docker info'."
  echo "  Run: sudo nvidia-ctk runtime configure --runtime=docker && sudo systemctl restart docker"
fi

# ── build ─────────────────────────────────────────────────────────────────────
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [[ $NO_BUILD -eq 0 ]]; then
  echo "Building $IMAGE (COLMAP 4.0.3 from source — first build ~20 min) ..."
  docker build -t "$IMAGE" "$REPO_ROOT"
else
  echo "Skipping build (--no-build)"
fi

# ── run handler with test input ───────────────────────────────────────────────
echo ""
echo "Running test job (num_frames=$NUM_FRAMES, timeout=${TIMEOUT}s) ..."

TEST_INPUT=$(printf '{"input":{"video_url":"%s","num_frames":%d,"matching":"sequential","gpu":true}}' \
  "$VIDEO_URL" "$NUM_FRAMES")

TMPLOG=$(mktemp)
trap 'rm -f "$TMPLOG"' EXIT

timeout "$TIMEOUT" docker run --rm --gpus all \
  "$IMAGE" \
  python3 handler.py --test_input "$TEST_INPUT" 2>&1 | tee "$TMPLOG" || {
  fail "Container exited non-zero or timed out after ${TIMEOUT}s"
}

# ── validate output ───────────────────────────────────────────────────────────
if ! grep -q "completed successfully" "$TMPLOG"; then
  fail "Did not find 'completed successfully' in output"
fi

if ! grep -q "'colmap_workspace_b64':" "$TMPLOG"; then
  fail "colmap_workspace_b64 key not found in output"
fi

LOGSIZE=$(wc -c < "$TMPLOG")
if [[ "$LOGSIZE" -lt 50000 ]]; then
  fail "Output suspiciously small (${LOGSIZE} bytes) — colmap_workspace_b64 likely empty"
fi

echo ""
pass "Job completed successfully, colmap_workspace_b64 present (${LOGSIZE} bytes)"

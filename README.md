# colmap-serverless

[![Runpod](https://api.runpod.io/badge/alx/colmap-serverless)](https://console.runpod.io/hub/alx/colmap-serverless)

Serverless [RunPod](https://www.runpod.io/) endpoint that runs [COLMAP](https://colmap.github.io/) structure-from-motion on drone or handheld MP4 video. Part of the [RunSplat](https://github.com/alx/runsplat) pipeline.

**Input:** one or more MP4 video URLs  
**Output:** COLMAP workspace (base64 tar.gz) ready for 3D Gaussian Splatting training

```
MP4 video(s)
    │
    ▼  ffmpeg — extract up to 150 frames
    │
    ▼  COLMAP feature_extractor
    │
    ▼  COLMAP sequential_matcher / exhaustive_matcher
    │
    ▼  COLMAP mapper (sparse reconstruction)
    │
    ▼  COLMAP image_undistorter
    │
    ▼  colmap_workspace.tar.gz (base64)
```

---

## Why Gaussian Splatting?

Traditional photogrammetry outputs meshes or point clouds. Gaussian Splatting is different: it lets you **fly through the scene and see it exactly as it is — from every angle — with real textures**.

- See your land as it really looks, not an abstraction
- Easier to understand than technical maps or wireframes
- Ideal for design reviews, planning, and client presentations
- Take remote measurements without revisiting the site
- No heavy software needed — runs in any modern browser
- Track construction progress or erosion over time

COLMAP is the industry-standard open-source Structure-from-Motion tool that computes camera poses from overlapping images, producing the sparse point cloud and calibrated cameras that Gaussian Splatting trainers like [Brush](https://github.com/ArthurBrussee/brush) need as input.

---

## Drone capture tips

For best COLMAP reconstruction results, **circular flight patterns** significantly outperform traditional grid surveys:

> *Unlike traditional grid or double-grid patterns, Circlegrammetry enables drones to fly in circular patterns, with the camera angled between 45° and 70° toward the center of each circle. This method captures images from more angles in fewer flights.*
>
> — [SPH Engineering, Circlegrammetry](https://www.sphengineering.com/news/sph-engineering-launches-circlegrammetry-a-game-changer-in-drone-photogrammetry)

More viewing angles = more robust feature matching = better COLMAP reconstruction = better Gaussian Splat.

---

## Stack

| Component | Version | Role |
|-----------|---------|------|
| [COLMAP](https://github.com/colmap/colmap) | 4.0.3 | Structure-from-Motion |
| [ffmpeg](https://ffmpeg.org/) | system | Frame extraction |
| CUDA | 12.9 | GPU feature extraction |
| [RunPod SDK](https://docs.runpod.io/serverless/workers/handlers/overview) | latest | Serverless handler |
| Base image | `nvidia/cuda:12.9.0-devel-ubuntu24.04` | Build stage |
| Runtime image | `nvidia/cuda:12.9.0-base-ubuntu24.04` | Runtime stage |

---

## API

### Input

```json
{
  "input": {
    "video_url": "https://example.com/drone-flight.mp4",
    "num_frames": 150,
    "matching": "sequential",
    "camera_model": "SIMPLE_RADIAL",
    "sequential_overlap": 10,
    "quality": "high",
    "gpu": true
  }
}
```

Multiple videos (combined into one reconstruction):

```json
{
  "input": {
    "video_urls": [
      "https://example.com/pass-north.mp4",
      "https://example.com/pass-south.mp4"
    ],
    "num_frames": 200,
    "matching": "sequential"
  }
}
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `video_url` | string | — | Single MP4 URL |
| `video_urls` | string[] | — | Multiple MP4 URLs (combined reconstruction) |
| `num_frames` | int | `150` | Max frames extracted per video, spread evenly across duration |
| `matching` | string | `sequential` | `sequential` for video; `exhaustive` for unordered image sets |
| `camera_model` | string | `SIMPLE_RADIAL` | See [camera models](#camera-models) below |
| `sequential_overlap` | int | `10` | Adjacent frames to match per frame in sequential mode |
| `quality` | string | `high` | Feature extraction quality: `low` / `medium` / `high` / `extreme` |
| `gpu` | bool | `true` | GPU SIFT feature extraction and matching |

#### Camera models

| Model | Use case |
|-------|----------|
| `SIMPLE_RADIAL` | Standard video from phone or most drones |
| `RADIAL` | Higher distortion lenses |
| `OPENCV` | Known radial + tangential lens distortion |
| `OPENCV_FISHEYE` | Wide-angle or fisheye drone cameras |
| `PINHOLE` | Pre-calibrated camera, no distortion correction |

### Output

```json
{
  "colmap_workspace_b64": "<base64 tar.gz of colmap/ directory>",
  "colmap_version": "4.0.3",
  "num_frames_extracted": 147,
  "status": "done"
}
```

The `colmap_workspace_b64` field contains a gzipped tar archive of the `colmap/` directory, which includes:

```
colmap/
├── database.db          # Feature match database
├── images/              # Undistorted frames (Brush input)
└── sparse/0/            # Camera poses + sparse point cloud
    ├── cameras.bin
    ├── images.bin
    └── points3D.bin
```

Pass this directly to [brush-serverless](https://github.com/alx/brush-serverless) as `colmap_workspace_b64`.

---

## Local build & test

### Requirements

- Docker with [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html)
- NVIDIA GPU with CUDA 12.9 driver support

### Build

```bash
# First build compiles COLMAP 4.0.3 from source — allow ~20–30 min
docker build -t colmap-serverless:local .

# Stream output and save log
docker build -t colmap-serverless:local . 2>&1 | tee /tmp/build.log

# Filter for errors only
docker build -t colmap-serverless:local . 2>&1 | grep -E "^(ERROR|Step|error|failed)"
```

### Test

```bash
./scripts/test_local.sh

# Skip rebuild if already built
./scripts/test_local.sh --no-build
```

The test downloads `lighthouse.mp4`, extracts 30 frames, runs the full COLMAP pipeline, and validates that `colmap_workspace_b64` is present and non-empty in the output.

### Manual run

```bash
docker run --rm --gpus all colmap-serverless:local \
  python3 handler.py --test_input '{
    "input": {
      "video_url": "https://github.com/alx/runsplat/releases/download/v0.1.5/lighthouse.mp4",
      "num_frames": 30,
      "matching": "sequential",
      "gpu": true
    }
  }'
```

### COLMAP build-only stage

Test that COLMAP compiles without running the handler:

```bash
docker build --target colmap-builder -t colmap-builder . 2>&1 | tee /tmp/build-colmap.log
```

---

## Publishing to RunPod Hub

1. Verify the local build and test pass
2. Push to GitHub and create a release: `gh release create v1.0.0 --generate-notes`
3. RunPod Hub detects the release, builds the image, and runs `.runpod/tests.json`
4. After tests pass, submit for review on the [Hub page](https://www.runpod.io/console/hub)

Configuration is in `.runpod/hub.json`. Available presets:
- **Standard drone video** — 150 frames, sequential matching, SIMPLE_RADIAL
- **Wide-angle / fisheye drone** — 150 frames, sequential matching, OPENCV_FISHEYE
- **Dense / thorough reconstruction** — 300 frames, exhaustive matching

---

## COLMAP documentation

- [COLMAP documentation](https://colmap.github.io/tutorial.html)
- [Feature extraction options](https://colmap.github.io/tutorial.html#feature-detection-and-extraction)
- [Matching strategies](https://colmap.github.io/tutorial.html#feature-matching-and-geometric-verification)
- [Camera models reference](https://colmap.github.io/cameras.html)
- [GitHub repository](https://github.com/colmap/colmap)

---

## Related repos

| Repo | Role |
|------|------|
| [runsplat](https://github.com/alx/runsplat) | Full pipeline orchestrator + result viewer |
| [brush-serverless](https://github.com/alx/brush-serverless) | 3D Gaussian Splatting training (takes this output) |

---

## Credits

- [COLMAP](https://github.com/colmap/colmap) — Structure-from-Motion and MVS
- [RunPod](https://www.runpod.io/) — Serverless GPU infrastructure
- [SPH Engineering](https://www.sphengineering.com/news/sph-engineering-launches-circlegrammetry-a-game-changer-in-drone-photogrammetry) — Circlegrammetry technique

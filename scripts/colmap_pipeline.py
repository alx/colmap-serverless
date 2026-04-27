#!/usr/bin/env python3
"""COLMAP pipeline: video → frames → SfM reconstruction → colmap/ workspace."""

import argparse
import os
import subprocess
import sys
from pathlib import Path


def run(cmd: list, **kwargs):
    print(f"+ {' '.join(str(c) for c in cmd)}", flush=True)
    subprocess.run(cmd, check=True, **kwargs)


def get_frame_count(mp4_path: Path) -> int:
    result = subprocess.run(
        [
            "ffprobe", "-v", "quiet", "-select_streams", "v:0",
            "-count_packets", "-show_entries", "stream=nb_read_packets",
            "-of", "csv=p=0", str(mp4_path),
        ],
        capture_output=True, text=True, check=True,
    )
    return int(result.stdout.strip())


def detect_colmap_gpu_flags() -> tuple[str, str]:
    try:
        result = subprocess.run(
            ["colmap", "feature_extractor", "--help"],
            capture_output=True, text=True, timeout=10,
        )
        combined = result.stdout + result.stderr
        if "FeatureExtraction.use_gpu" in combined:
            return "FeatureExtraction.use_gpu", "FeatureMatching.use_gpu"
    except Exception:
        pass
    return "SiftExtraction.use_gpu", "SiftMatching.use_gpu"


def extract_frames(mp4_path: Path, frames_dir: Path, step: int, prefix: str):
    frames_dir.mkdir(parents=True, exist_ok=True)
    run([
        "ffmpeg", "-i", str(mp4_path),
        "-vf", f"select=not(mod(n\\,{step}))",
        "-vsync", "vfr",
        str(frames_dir / f"{prefix}_frame_%04d.png"),
    ])


def run_colmap(
    project_dir: Path,
    use_gpu: bool,
    matching: str,
    camera_model: str,
    sequential_overlap: int,
    quality: str,
    feature_flag: str,
    matching_flag: str,
):
    gpu_val = "1" if use_gpu else "0"
    colmap_dir = project_dir / "colmap"
    frames_dir = project_dir / "frames"
    (colmap_dir / "distorted" / "sparse").mkdir(parents=True, exist_ok=True)
    database = colmap_dir / "database.db"
    colmap_env = {**os.environ, "QT_QPA_PLATFORM": "offscreen"}

    quality_flag = feature_flag.replace(".use_gpu", ".quality")
    run([
        "colmap", "feature_extractor",
        "--database_path", str(database),
        "--image_path", str(frames_dir),
        "--ImageReader.single_camera", "1",
        "--ImageReader.camera_model", camera_model,
        f"--{feature_flag}", gpu_val,
        f"--{quality_flag}", quality,
    ], env=colmap_env)

    matcher = "sequential_matcher" if matching == "sequential" else "exhaustive_matcher"
    matcher_args = [
        "colmap", matcher,
        "--database_path", str(database),
        f"--{matching_flag}", gpu_val,
    ]
    if matching == "sequential":
        matcher_args += ["--SequentialMatching.overlap", str(sequential_overlap)]
    run(matcher_args, env=colmap_env)

    run([
        "colmap", "mapper",
        "--database_path", str(database),
        "--image_path", str(frames_dir),
        "--output_path", str(colmap_dir / "distorted" / "sparse"),
        "--Mapper.ba_global_function_tolerance=0.000001",
    ], env=colmap_env)

    sparse_0 = colmap_dir / "distorted" / "sparse" / "0"
    if not sparse_0.exists():
        found = sorted((colmap_dir / "distorted" / "sparse").glob("*"))
        print(
            f"Error: COLMAP mapper produced no reconstruction (sparse/0 missing).\n"
            f"  Expected: {sparse_0}\n"
            f"  Found: {[p.name for p in found] or 'nothing'}\n"
            f"  Too few inlier feature matches — try a slower video or --matching exhaustive.",
            file=sys.stderr,
        )
        sys.exit(1)

    run([
        "colmap", "image_undistorter",
        "--image_path", str(frames_dir),
        "--input_path", str(sparse_0),
        "--output_path", str(colmap_dir),
        "--output_type", "COLMAP",
    ], env=colmap_env)


def main():
    parser = argparse.ArgumentParser(description="COLMAP pipeline: video → SfM workspace")
    parser.add_argument("--project", required=True, type=Path,
                        help="Project directory containing input/ with MP4 files")
    parser.add_argument("--num-frames", type=int, default=150,
                        help="Max frames to extract per video (default: 150)")
    parser.add_argument("--matching", choices=["sequential", "exhaustive"], default="sequential",
                        help="Feature matching strategy (default: sequential)")
    parser.add_argument("--camera-model",
                        choices=["SIMPLE_RADIAL", "RADIAL", "OPENCV", "OPENCV_FISHEYE", "PINHOLE"],
                        default="SIMPLE_RADIAL",
                        help="COLMAP camera model (default: SIMPLE_RADIAL)")
    parser.add_argument("--sequential-overlap", type=int, default=10,
                        help="Adjacent frames to match in sequential mode (default: 10)")
    parser.add_argument("--quality", choices=["low", "medium", "high", "extreme"], default="high",
                        help="Feature extraction quality (default: high)")
    parser.add_argument("--gpu", action="store_true",
                        help="Enable GPU SIFT extraction/matching")
    args = parser.parse_args()

    project_dir = args.project.resolve()
    input_dir = project_dir / "input"

    if not input_dir.exists():
        print(f"Error: {input_dir} not found", file=sys.stderr)
        sys.exit(1)

    mp4s = sorted(input_dir.glob("*.mp4"))
    if not mp4s:
        print(f"Error: No .mp4 files in {input_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"Project: {project_dir.name}", flush=True)
    print(f"Videos: {[f.name for f in mp4s]}", flush=True)

    feature_flag, matching_flag = detect_colmap_gpu_flags()
    print(f"COLMAP GPU flags: {feature_flag} / {matching_flag}", flush=True)

    target_per_video = max(50, args.num_frames // len(mp4s))
    frames_dir = project_dir / "frames"
    for mp4 in mp4s:
        total = get_frame_count(mp4)
        step = max(1, total // target_per_video)
        print(f"\n[frames] {mp4.name}: {total} total, extracting every {step}th frame", flush=True)
        extract_frames(mp4, frames_dir, step, mp4.stem)

    print("\n[colmap] Running COLMAP reconstruction...", flush=True)
    run_colmap(
        project_dir,
        use_gpu=args.gpu,
        matching=args.matching,
        camera_model=args.camera_model,
        sequential_overlap=args.sequential_overlap,
        quality=args.quality,
        feature_flag=feature_flag,
        matching_flag=matching_flag,
    )

    print(f"\nDone! Workspace: {project_dir / 'colmap'}", flush=True)


if __name__ == "__main__":
    main()

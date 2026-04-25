import base64
import subprocess
import tarfile
import tempfile
import urllib.request
from pathlib import Path

import runpod

COLMAP_VERSION = "4.0.3"


def handler(event):
    inp = event["input"]

    raw = inp.get("video_urls") or inp.get("video_url")
    if not raw:
        return {"error": "Provide video_url (string) or video_urls (list of strings)"}
    video_urls = raw if isinstance(raw, list) else [raw]

    num_frames   = int(inp.get("num_frames", 150))
    matching     = str(inp.get("matching", "sequential"))
    camera_model = str(inp.get("camera_model", "SIMPLE_RADIAL"))
    seq_overlap  = int(inp.get("sequential_overlap", 10))
    quality      = str(inp.get("quality", "high"))
    gpu          = bool(inp.get("gpu", True))

    if matching not in ("sequential", "exhaustive"):
        return {"error": f"matching must be 'sequential' or 'exhaustive', got: {matching}"}
    if camera_model not in ("SIMPLE_RADIAL", "RADIAL", "OPENCV", "OPENCV_FISHEYE", "PINHOLE"):
        return {"error": f"Unsupported camera_model: {camera_model}"}
    if quality not in ("low", "medium", "high", "extreme"):
        return {"error": f"quality must be low/medium/high/extreme, got: {quality}"}

    with tempfile.TemporaryDirectory() as tmp:
        project_dir = Path(tmp) / "project"
        input_dir = project_dir / "input"
        input_dir.mkdir(parents=True)

        for i, url in enumerate(video_urls):
            dest = input_dir / f"video_{i:02d}.mp4"
            print(f"Downloading {url} → {dest.name}", flush=True)
            urllib.request.urlretrieve(url, dest)

        cmd = [
            "python3", "/app/scripts/colmap_pipeline.py",
            "--project", str(project_dir),
            "--num-frames", str(num_frames),
            "--matching", matching,
            "--camera-model", camera_model,
            "--sequential-overlap", str(seq_overlap),
            "--quality", quality,
        ]
        if gpu:
            cmd.append("--gpu")

        result = subprocess.run(cmd, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            return {"error": f"COLMAP pipeline failed (exit {result.returncode}):\n{result.stderr[-3000:]}"}

        colmap_dir = project_dir / "colmap"
        frames_extracted = len(list((project_dir / "frames").glob("*.png"))) if (project_dir / "frames").exists() else 0

        tarball = Path(tmp) / "colmap_workspace.tar.gz"
        with tarfile.open(tarball, "w:gz") as tar:
            tar.add(colmap_dir, arcname="colmap")

        workspace_b64 = base64.b64encode(tarball.read_bytes()).decode()

    return {
        "colmap_workspace_b64": workspace_b64,
        "colmap_version": COLMAP_VERSION,
        "num_frames_extracted": frames_extracted,
        "status": "done",
    }


runpod.serverless.start({"handler": handler})

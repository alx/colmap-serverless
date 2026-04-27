import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

import requests
import runpod

COLMAP_VERSION = "4.0.3"


def _download_gofile(url, dest):
    sys.path.insert(0, "/app/scripts")
    from gofile_downloader import Manager as _GofileManager  # noqa: PLC0415
    with tempfile.TemporaryDirectory() as dl_dir:
        os.environ["GF_DOWNLOAD_DIR"] = dl_dir
        _GofileManager(url_or_file=url).run()
        mp4s = sorted(Path(dl_dir).rglob("*.mp4"))
        if not mp4s:
            raise RuntimeError(f"No MP4 found in gofile share: {url}")
        shutil.move(str(mp4s[0]), str(dest))


def _upload_gofile(path: Path) -> str:
    server = requests.get("https://api.gofile.io/servers", timeout=30).json()["data"]["servers"][0]["name"]
    with open(path, "rb") as fh:
        resp = requests.post(
            f"https://{server}.gofile.io/uploadFile",
            files={"file": fh},
            timeout=300,
        ).json()
    return resp["data"]["downloadPage"]


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
    gpu          = bool(inp.get("gpu", True))

    if matching not in ("sequential", "exhaustive"):
        return {"error": f"matching must be 'sequential' or 'exhaustive', got: {matching}"}
    if camera_model not in ("SIMPLE_RADIAL", "RADIAL", "OPENCV", "OPENCV_FISHEYE", "PINHOLE"):
        return {"error": f"Unsupported camera_model: {camera_model}"}

    with tempfile.TemporaryDirectory() as tmp:
        project_dir = Path(tmp) / "project"
        input_dir = project_dir / "input"
        input_dir.mkdir(parents=True)

        for i, url in enumerate(video_urls):
            dest = input_dir / f"video_{i:02d}.mp4"
            print(f"Downloading {url} → {dest.name}", flush=True)
            if urllib.parse.urlparse(url).netloc in ("gofile.io", "www.gofile.io"):
                _download_gofile(url, dest)
            else:
                urllib.request.urlretrieve(url, dest)

        cmd = [
            "python3", "/app/scripts/colmap_pipeline.py",
            "--project", str(project_dir),
            "--num-frames", str(num_frames),
            "--matching", matching,
            "--camera-model", camera_model,
            "--sequential-overlap", str(seq_overlap),
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
            # Only include undistorted images + sparse model.
            # Excluding distorted/ avoids duplicate cameras.bin/images.bin entries
            # that would cause Brush to pick the wrong (distorted) camera poses.
            tar.add(colmap_dir / "images", arcname="colmap/images")
            tar.add(colmap_dir / "sparse", arcname="colmap/sparse")

        print("Uploading workspace to GoFile.io…", flush=True)
        workspace_url = _upload_gofile(tarball)

    return {
        "colmap_workspace_url": workspace_url,
        "colmap_version": COLMAP_VERSION,
        "num_frames_extracted": frames_extracted,
        "status": "done",
    }


runpod.serverless.start({"handler": handler})

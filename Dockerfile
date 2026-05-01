# ── Build args ────────────────────────────────────────────────────────────────
# cuda12.5 target: CUDA_VERSION=12.5.1  UBUNTU_VERSION=24.04  (default/latest)
# cuda12.4 target: CUDA_VERSION=12.4.1  UBUNTU_VERSION=22.04
#
# ubuntu24.04 images start at CUDA 12.5.1 on Docker Hub.
# ubuntu22.04 goes back to CUDA 12.4.1, covering older host drivers.
ARG CUDA_VERSION=12.5.1
ARG UBUNTU_VERSION=24.04

# ── Stage 1: build COLMAP 4.0.3 from source ───────────────────────────────────
FROM nvidia/cuda:${CUDA_VERSION}-devel-ubuntu${UBUNTU_VERSION} AS colmap-builder
ARG UBUNTU_VERSION=24.04
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    ccache cmake ninja-build build-essential git \
    libboost-program-options-dev libboost-graph-dev libboost-system-dev \
    libeigen3-dev libopenimageio-dev openimageio-tools libopenexr-dev \
    libmetis-dev libgoogle-glog-dev libgtest-dev libgmock-dev \
    libsqlite3-dev libglew-dev \
    qt6-base-dev libqt6opengl6-dev libqt6openglwidgets6 libqt6svg6-dev \
    libcgal-dev libceres-dev libcurl4-openssl-dev libssl-dev \
    libopenblas-dev \
    && rm -rf /var/lib/apt/lists/*

# Required by OpenImageIO CMake config even when OpenCV support is unused
RUN mkdir -p /usr/include/opencv4

RUN git clone --depth 1 --branch 4.0.3 \
    https://github.com/colmap/colmap.git /colmap \
    && cd /colmap && mkdir build && cd build \
    && cmake .. -GNinja \
        "-DCMAKE_CUDA_ARCHITECTURES=50;60;70;80;90" \
        -DCMAKE_INSTALL_PREFIX=/colmap-install \
        -DONNX_ENABLED=OFF \
        -DTESTS_ENABLED=OFF \
    && ninja -j2 install

# ── Stage 2: runtime ──────────────────────────────────────────────────────────
FROM nvidia/cuda:${CUDA_VERSION}-base-ubuntu${UBUNTU_VERSION}
ARG UBUNTU_VERSION=24.04
ENV DEBIAN_FRONTEND=noninteractive
ENV NVIDIA_DRIVER_CAPABILITIES=compute,utility
ENV QT_QPA_PLATFORM=offscreen

# Runtime package names differ between ubuntu22.04 and ubuntu24.04.
# ubuntu24.04 appended t64 suffixes and bumped library versions.
RUN apt-get update && \
    if [ "$UBUNTU_VERSION" = "24.04" ]; then \
      apt-get install -y \
        ffmpeg python3 python3-pip curl \
        libboost-program-options1.83.0 libgl1 libglib2.0-0 \
        libmetis5 libceres4t64 libopenimageio2.4t64 libglew2.2 \
        libgoogle-glog0v6t64 \
        libqt6core6 libqt6gui6 libqt6widgets6 libqt6openglwidgets6 libqt6svg6 \
        libcurl4 libssl3t64 libopenblas0; \
    else \
      apt-get install -y \
        ffmpeg python3 python3-pip curl \
        libboost-program-options1.74.0 libgl1 libglib2.0-0 \
        libmetis5 libceres2 libopenimageio2.2 libglew2.2 \
        libgoogle-glog0v5 \
        libqt6core6 libqt6gui6 libqt6widgets6 libqt6openglwidgets6 libqt6svg6 \
        libcurl4 libssl3 libopenblas0; \
    fi \
    && rm -rf /var/lib/apt/lists/*

COPY --from=colmap-builder /colmap-install/ /usr/local/

WORKDIR /app
RUN if [ "$UBUNTU_VERSION" = "24.04" ]; then \
      pip3 install --no-cache-dir --break-system-packages runpod requests; \
    else \
      pip3 install --no-cache-dir runpod requests; \
    fi

COPY scripts/colmap_pipeline.py /app/scripts/colmap_pipeline.py
COPY scripts/gofile_downloader.py /app/scripts/gofile_downloader.py
COPY vastai_entrypoint.sh /app/vastai_entrypoint.sh
COPY handler.py /app/handler.py

ARG VASTAI=0
RUN if [ "$VASTAI" = "1" ]; then \
      cp /app/vastai_entrypoint.sh /entrypoint.sh; \
    else \
      echo '#!/bin/sh\nexec python3 -u /app/handler.py "$@"' > /entrypoint.sh; \
    fi
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]

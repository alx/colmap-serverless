# ── Stage 1: build COLMAP 4.0.3 from source ──────────────────────────────────
FROM nvidia/cuda:12.9.0-devel-ubuntu24.04 AS colmap-builder
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    ccache cmake ninja-build build-essential git \
    libboost-program-options-dev libboost-graph-dev libboost-system-dev \
    libeigen3-dev libopenimageio-dev openimageio-tools \
    libmetis-dev libgoogle-glog-dev libgtest-dev libgmock-dev \
    libsqlite3-dev libglew-dev \
    qt6-base-dev libqt6opengl6-dev libqt6openglwidgets6 libqt6svg6-dev \
    libcgal-dev libceres-dev libcurl4-openssl-dev libssl-dev \
    libmkl-full-dev \
    && rm -rf /var/lib/apt/lists/*

# Required by OpenImageIO CMake config even when OpenCV support is unused
RUN mkdir -p /usr/include/opencv4

RUN git clone --depth 1 --branch 4.0.3 \
    https://github.com/colmap/colmap.git /colmap \
    && cd /colmap && mkdir build && cd build \
    && cmake .. -GNinja \
        -DCMAKE_CUDA_ARCHITECTURES=all-major \
        -DCMAKE_INSTALL_PREFIX=/colmap-install \
        -DONNX_ENABLED=OFF \
        -DTESTS_ENABLED=OFF \
        -DBLA_VENDOR=Intel10_64lp \
    && ninja -j$(nproc) install

# ── Stage 2: runtime ──────────────────────────────────────────────────────────
FROM nvidia/cuda:12.9.0-base-ubuntu24.04
ENV DEBIAN_FRONTEND=noninteractive
ENV NVIDIA_DRIVER_CAPABILITIES=compute,utility
ENV QT_QPA_PLATFORM=offscreen

RUN apt-get update && apt-get install -y \
    ffmpeg python3 python3-pip curl \
    libboost-program-options1.83.0 libgl1 libglib2.0-0 \
    libmetis5 libceres4t64 libopenimageio2.4t64 libglew2.2 \
    libgoogle-glog0v6t64 \
    libqt6core6 libqt6gui6 libqt6widgets6 libqt6openglwidgets6 libqt6svg6 \
    libcurl4 libssl3t64 \
    libmkl-intel-lp64 libmkl-intel-thread libmkl-core libomp5 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=colmap-builder /colmap-install/ /usr/local/

WORKDIR /app
RUN pip3 install --no-cache-dir --break-system-packages runpod

COPY scripts/colmap_pipeline.py /app/scripts/colmap_pipeline.py
COPY handler.py /app/handler.py

CMD ["python3", "-u", "handler.py"]

# SPDX-License-Identifier: MIT
FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive
ARG http_proxy
ARG https_proxy
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc-aarch64-linux-gnu binutils-aarch64-linux-gnu \
    gcc-arm-linux-gnueabihf binutils-arm-linux-gnueabihf bison flex swig \
    libssl-dev libgnutls28-dev python3 python3-dev python3-setuptools python3-pyelftools \
    device-tree-compiler bc mtools dosfstools fdisk u-boot-tools \
    xz-utils lz4 cpio file ca-certificates curl rsync git \
    squashfs-tools fakeroot gzip qemu-user-static kmod && rm -rf /var/lib/apt/lists/*

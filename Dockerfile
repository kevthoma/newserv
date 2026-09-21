# syntax=docker/dockerfile:1

ARG BASE_IMAGE=ubuntu:24.04
FROM ${BASE_IMAGE} AS builder

RUN apt update && apt install -y --no-install-recommends \
    python3 \
    git \
    ca-certificates \
    sudo \
    make \
    cmake \
    g++ \
    libasio-dev \
    zlib1g-dev

# ---

FROM builder AS deps

# Pinned, not master. Both dependencies are cloned at build time, so tracking master made every
# image only as reproducible as upstream's last push -- resource_dasm/phosg API changes between
# 2026-09-18 and 09-20 broke every build of this fork (AddressTranslator.cc: FileAnalysis::Function
# has no member 'label'). These are the commits this source is known to compile against. Bump them
# deliberately, and build the canary first. (Pinning also keeps the gha layer cache honest: the clone
# command text now changes whenever what it fetches changes.)
ARG PHOSG_TARGET=5368a493eb4cf2293118f8596c3c3b0e63b50550
ARG RESOURCE_DASM_TARGET=2142f1e6f960d737cf2f9c6d07cbb283aeb106fc
ARG BUILD_RESOURCE_DASM=true

# `git clone -b` only accepts branch or tag names; fetching the ref directly also accepts a commit SHA.
RUN git init -q phosg && cd phosg && \
    git fetch -q --depth 1 https://github.com/fuzziqersoftware/phosg.git ${PHOSG_TARGET} && \
    git checkout -q FETCH_HEAD && \
    cmake . && \
    make -j$(nproc) && \
    sudo make install

RUN \
    if [ "$BUILD_RESOURCE_DASM" = "true" ] ; then \
    git init -q resource_dasm && cd resource_dasm && \
    git fetch -q --depth 1 https://github.com/fuzziqersoftware/resource_dasm.git ${RESOURCE_DASM_TARGET} && \
    git checkout -q FETCH_HEAD && \
    cmake . && \
    make -j$(nproc) && \
    sudo make install \
    ; fi

# ---

FROM builder AS newserv

ARG BUILD_TYPE=Release
ARG BUILD_STRIP=true

WORKDIR /usr/src/newserv
COPY . .
COPY --from=deps /usr/local /usr/local

RUN cmake -B $PWD/build -DCMAKE_BUILD_TYPE=${BUILD_TYPE} && \
    cmake --build $PWD/build --config ${BUILD_TYPE} -j $(nproc) && \
    sudo make -C build install

RUN \
    if [ "$BUILD_STRIP" = "true" ] ; then \
    strip /usr/local/lib/*.a && \
    strip /usr/local/bin/* \
    ; fi

# ---

FROM ${BASE_IMAGE} AS data

WORKDIR /newserv
COPY system/ ./system
RUN cp -f system/config.example.json system/config.json && \
    sed -i 's/"ExternalAddress": "[^"]*"/"ExternalAddress": "0.0.0.0"/' system/config.json

# ---

FROM ${BASE_IMAGE} AS final

# libasio-dev: runtime dep. iproute2: lets the entrypoint detect the container's LAN IP. curl +
# ca-certificates: the entrypoint's ExternalAddress auto-sync fetches the public IP over HTTPS and
# calls the local reload-config API (see docker-entrypoint.sh).
RUN apt update && apt install -y --no-install-recommends \
    libasio-dev \
    iproute2 \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/* /var/cache/apt/*

WORKDIR /newserv
COPY --from=data /newserv .
COPY --from=newserv /usr/local /usr/local

# Keep a pristine copy of the baked system/ dir OUTSIDE the volume. When an empty host dir is
# bind-mounted at /newserv/system it shadows the baked defaults; the entrypoint seeds them back
# from here on first boot. This RUN must come BEFORE the VOLUME line so the copy is baked into the
# image layer rather than into the (empty) volume.
RUN cp -a /newserv/system /newserv/system-default

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

USER root
VOLUME /newserv/system

# does not allow receiving any signal at the moment, so force kill the app
STOPSIGNAL SIGKILL
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["newserv"]

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

ARG PHOSG_TARGET=master
ARG RESOURCE_DASM_TARGET=master
ARG BUILD_RESOURCE_DASM=true

RUN git clone --depth 1 -b ${PHOSG_TARGET} https://github.com/fuzziqersoftware/phosg.git && \
    cd phosg && \
    cmake . && \
    make -j$(nproc) && \
    sudo make install

RUN \
    if [ "$BUILD_RESOURCE_DASM" = "true" ] ; then \
    git clone --depth 1 -b ${RESOURCE_DASM_TARGET} https://github.com/fuzziqersoftware/resource_dasm.git && \
    cd resource_dasm && \
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

# libasio-dev: runtime dep. iproute2: lets the entrypoint detect the container's LAN IP to stamp into
# the seeded config (see docker-entrypoint.sh). tzdata: so the TZ env resolves to a real timezone,
# which localtime() (the in-game "Internet Time" clock) honors instead of falling back to UTC.
RUN apt update && apt install -y --no-install-recommends \
    libasio-dev \
    iproute2 \
    tzdata \
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

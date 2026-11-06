# The WebSDR for the Pi: board bridge, GNU Radio engine, FT8 decoder and web server in one image; docker-compose.yml runs
# each as its own service. Build from code/ (the context needs radiolib/ and gnu-radio/ too):
#
#   docker buildx build --platform linux/arm64 -f websdr/sdr/Dockerfile -t websdr:latest --load .

# ft8_lib's decode_ft8 (MIT, https://github.com/kgoba/ft8_lib), at a fixed commit. Only the executable is kept.
FROM debian:trixie-slim AS ft8_lib
RUN apt-get update \
 && apt-get install -y --no-install-recommends gcc make libc6-dev git ca-certificates \
 && git clone https://github.com/kgoba/ft8_lib /ft8_lib \
 && cd /ft8_lib \
 && git checkout 9fec6ca39886edbf96f4f5e71edc76da5074e871 \
 && make decode_ft8

FROM debian:trixie-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      gnuradio python3-pip \
      python3-zmq python3-numpy python3-scipy python3-serial \
      python3-fastapi python3-uvicorn python3-websockets python3-psutil \
 && rm -rf /var/lib/apt/lists/*

COPY --from=ft8_lib /ft8_lib/decode_ft8 /usr/local/bin/decode_ft8

ENV PYTHONUNBUFFERED=1
WORKDIR /opt/websdr

# radiolib's ft8 extra (ldpc) isn't needed here, so no dependencies from pip; apt has the rest.
COPY radiolib /opt/radiolib
RUN pip install --no-deps --break-system-packages /opt/radiolib

COPY gnu-radio/iq_bridge.py ./
COPY websdr/sdr/ ./sdr/
RUN grcc -o build sdr/engine.grc

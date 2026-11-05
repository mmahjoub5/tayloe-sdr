# The WebSDR for the Pi: board bridge, GNU Radio engine and web server in one image; docker-compose.yml runs
# each as its own service. Build from code/ (the context needs radiolib/ and gnu-radio/ too):
#
#   docker buildx build --platform linux/arm64 -f websdr/sdr/Dockerfile -t websdr:latest --load .

FROM debian:trixie-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      gnuradio python3-pip \
      python3-zmq python3-numpy python3-scipy python3-serial \
      python3-fastapi python3-uvicorn python3-websockets python3-psutil \
 && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1
WORKDIR /opt/websdr

# radiolib's ft8 extra (ldpc) isn't needed here, so no dependencies from pip; apt has the rest.
COPY radiolib /opt/radiolib
RUN pip install --no-deps --break-system-packages /opt/radiolib

COPY gnu-radio/iq_bridge.py ./
COPY websdr/sdr/ ./sdr/
RUN grcc -o build sdr/engine.grc

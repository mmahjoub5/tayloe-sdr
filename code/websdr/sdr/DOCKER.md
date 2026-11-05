# WebSDR on the Pi with Docker

One image (`Dockerfile`), three services (`docker-compose.yml`: bridge, engine, server). No registry.

## Build on the Pi (from `code/` on the Mac)

The sources are a few MB; the Pi downloads GNU Radio itself (the first build takes a while, later ones reuse
the apt layer).

    COPYFILE_DISABLE=1 tar --exclude __pycache__ --exclude '*.egg-info' --exclude websdr/sdr/build \
        -cf - radiolib gnu-radio/iq_bridge.py websdr/sdr \
      | ssh pi@10.0.0.216 'rm -rf ~/websdr-src && mkdir ~/websdr-src && tar -xf - -C ~/websdr-src \
          && cp ~/websdr-src/websdr/sdr/docker-compose.yml ~/websdr/'
    ssh pi@10.0.0.216 'cd ~/websdr-src && docker build -f websdr/sdr/Dockerfile -t websdr:latest .'

Or build on the Mac (arm64 too, so no emulation) and copy the image; this needs several GB free on the Mac:

    docker buildx build --platform linux/arm64 -f websdr/sdr/Dockerfile -t websdr:latest --load .
    docker save websdr:latest | gzip | ssh pi@10.0.0.216 'gunzip | docker load'

## First time on the Pi

    sudo apt install docker.io docker-compose        # Docker 26, Compose 2.26 on trixie
    sudo usermod -aG docker pi                       # log out and back in
    sudo systemctl disable --now rp2040-rtltcp      # only one program can open the board
    mkdir -p ~/websdr && echo "SDR_KEY=memagic" > ~/websdr/.env

OpenWebRX keeps the RTL dongle; its "Tayloe board" device stops working while this runs.

## Run

    cd ~/websdr && docker compose up -d             # http://10.0.0.216:8090/#key=memagic
    docker compose logs -f engine                   # or bridge, server
    docker compose down

After copying a new image: `docker compose up -d` again (it recreates the containers). Services restart on
their own after a crash or a reboot. The bridge exits if the board is unplugged and restarts until it's back;
the engine's Board Tuner repeats its frequency every 3 s, so the board comes back tuned.

Public access: point cloudflared at `http://localhost:8090`.

# meche — enclosures for the receiver

## The system

```
MLA-30+ loop ── coax ──> bias-T ──screws onto──> radio PCB SMA (J1)
                          ^ 5 V over USB from a Pi USB-A port
radio PCB (XIAO RP2040) USB-C ──cable──> Pi 3 B+ USB-A   (data + the radio's 5 V)
Pi 3 B+ <── micro-USB 5 V supply; runs the WebSDR / FT8 software
```

- **Bias-T:** a separate module that comes with the antenna. It screws directly onto the radio board's SMA, so it
  hangs off the outside of the case wall, and it takes 5 V from a Pi USB port. Any enclosure must leave enough SMA
  thread exposed for it to screw on, and room for its body outside the wall. It also needs a Pi USB port that's
  reachable from outside. Its power cable is fixed and ends in a USB-A plug. In `pi_enclosure.py` all Pi USB ports
  face inward, so the cable comes in through a hole split between base and lid (`BIAST_CABLE_D`; laid in before
  closing) in the back wall over the gap. A zip-tie anchor on the floor holds it, and it plugs into the Pi's back USB
  stack. The radio cable uses the front stack, so the two don't cross.
- **The radio board has no antenna bias-T.** `VBIAS`, `VBIAS_AMP` and `VBIAS_FPGA` in the schematic are the
  op-amp/mixer mid-rail reference, not DC on the antenna. Nothing puts DC on the SMA (J1 → L1 560 nH → C20 100 nF).
- **Power budget:** all USB devices share the Pi's supply (5 V 2.5 A, about 1.2 A across all USB ports). The radio
  and the bias-T/active antenna both draw from it.

## Boards

- **Radio PCB:** 70 × 70 × 1.42 mm and no mounting holes. Model: `../radio-project/radio-project.step` (KiCad export),
  board at X 0..70, Y 0..70, Z 0..1.42.
  - **SMA:** on the X = 0 edge at Y 14.17, Z 2.0. It's hand-soldered and sits further out than the model's 0.43 mm.
    `SMA_PROUD` (2.0 mm) allows for that. A printed case that didn't close was caused by this.
  - **USB-C:** the XIAO's port is on the Y = 70 edge at X 34.72, Z 3.81.
  - **Rotary encoder:** in the model at X 54..67, Y 43..57, but **not fitted**. It shows as an expected overlap with
    any lid; exclude it from fit checks.
  - **Underside:** only the SMA and the encoder leads go below the board.
- **Pi 3 B+:** `rpi-step/pi3bplus.step` (GrabCAD; matches the official drawing to ~1 mm).
  - The model is **Y-up**, centred on X: native (x, y, z) = (X + 42.5, 31.5 − Z, Y).
  - It has nothing under the board, so take the SD card and the GPIO pin tails from the official drawing.
  - Mounting holes are M2.5 at (3.5, 3.5), (61.5, 3.5), (3.5, 52.5), (61.5, 52.5).
  - USB and Ethernet stick out 2.5 mm past the board edge.
  - `rpi-step/RPI 3 *` is a downloaded reference case, for comparison only.

## Enclosure scripts (CadQuery, `.venv` = Python 3.12)

- **`cad/enclosure.py`:** radio-only box with a magnetic snap lid (6 × 2 mm magnets flush in both rims). Branch
  `magnetic-lid`.
- **`cad/pi_enclosure.py`:** radio + Pi in one box with an internal USB cable, 7 × M2.5 screws, adhesive pads under
  the radio, and vents over the Pi's SoC. Branch `pi-enclosure`. It prints fit checks against both boards and the
  cable keep-out; every overlap must be 0.
- Both write the outputs to `out/` (git-ignored), with bed-oriented print files in `out/**/print/`.
- **Print bed is 220 × 220 mm.** Check every layout against it.

Open work and review feedback are tracked in `TODO.md`.

## Design conventions (from the owner)

- Keep the outside a plain rounded box; nothing bulging out of the walls (rejected external corner bosses).
- Screws for now (magnets were tried; see `enclosure.py`).
- Parametrise clearances (plug lengths, `SMA_PROUD`, `LIP_CLR`, pad thickness); derive sizes from them, not
  from magic numbers.
- Report fit-check numbers and say plainly when something fails (bed size, thin walls), with the options.

## FreeCAD

Use the **FreeCAD MCP** (`mcp__freecad__*`) for anything in FreeCAD: viewing, screenshots, building `.FCStd` files
(see the `freecad-mcp` skill). Never launch FreeCAD from the shell. That means don't run `cad/to_fcstd.py`, and don't
run `cad/push_gdrive.sh` as it stands, because it calls `to_fcstd.py`.

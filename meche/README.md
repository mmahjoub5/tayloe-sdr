# meche — 3D-printed enclosure

Two-piece enclosure (base + lid) for the Tayloe SDR board,
generated from code. The board drops into the base, the lid closes over it at
the board's top surface, and snaps shut on neodymium magnets pressed into
both rims.

```
cad/enclosure.py      the radio-only enclosure (CadQuery) — edit this
cad/pi_enclosure.py   radio board + Raspberry Pi 3 B+ in one box (see below)
cad/to_fcstd.py       packs board + parts into a FreeCAD file for viewing
rpi-step/             Pi 3 B+ board model (pi3bplus.step) and a reference Pi case
out/                  generated files (git-ignored, rebuild any time)
```

The design is driven by `../radio-project/radio-project.step` (exported from
KiCad). Re-export that file when the board changes and rebuild.

## One-time setup

Needs Python 3.12 (CadQuery doesn't support 3.14 yet) and, for the FreeCAD
view, FreeCAD 1.1 in `/Applications`.

```sh
cd meche
python3.12 -m venv .venv
.venv/bin/pip install cadquery
```

## Generate files

From `meche/`:

```sh
# 1. build all parts (~7 s)
.venv/bin/python cad/enclosure.py out ../radio-project/radio-project.step

# 2. optional: FreeCAD file with the board inside a see-through lid
/Applications/FreeCAD.app/Contents/MacOS/FreeCAD "$PWD/cad/to_fcstd.py"
```

Step 2 briefly opens a FreeCAD window and closes it on its own. It has to run
in the GUI — `freecadcmd` saves no colours or transparency, and the board ends
up hidden inside an opaque box.

### What you get

| File | Use |
|---|---|
| `out/print/{base,lid}.{stl,3mf,step}` | **Send these to the printer.** Already oriented flat on the bed at Z = 0 |
| `out/enclosure_{base,lid}.step` | Parts in board coordinates, for CAD |
| `out/tayloe_sdr_enclosure_assembly.step` | Board + all parts assembled |
| `out/enclosure.FCStd` | Same assembly for FreeCAD; lid 70 % transparent |

The FreeCAD file contains plain solids with no feature history — make changes
in `enclosure.py`, not in FreeCAD.

### Upload to Google Drive

Needs [Google Drive for desktop](https://www.google.com/drive/download/)
running and signed in.

```sh
cad/push_gdrive.sh              # rebuild, then copy to Drive
cad/push_gdrive.sh --no-build   # copy what's already in out/
```

Each run creates `My Drive/radio-project/print-files/<MM-DD>-<commit>/` with
`print/`, the assembly STEP, `enclosure.FCStd` and a `VERSION.txt` naming the
commit; Drive uploads it in the background. Uncommitted design changes get a
`-dirty` suffix, so commit first if you want a clean name. Set `DRIVE_DIR` to
copy somewhere else.

## Printing

| Part | Orientation | Supports |
|---|---|---|
| base | bottom down | none |
| lid | flipped, top face down (engraving on the bed) | none |

PETG or PLA, 0.2 mm layers, 3 walls. Prefer `lid.step` if your slicer takes
STEP (PrusaSlicer, Bambu Studio, OrcaSlicer): the lid STL has ~100 tiny
self-intersections inside the engraved letters. Slicers repair them
automatically, but STEP avoids them.

Hardware: 8 × 6 × 2 mm neodymium disc magnets (4 per half; 4 total with
`MAGNET_LAYOUT = "sides"`), 4 × 8 mm stick-on rubber feet (they sit in 0.6 mm
pockets on the bottom).

### Fitting the magnets

Each half has open recesses in its mating face, one per corner, sized
6.2 × 2.0 mm so the magnets press in flush and touch face to face when the lid
is on. A lip on the base rim drops into a groove in the lid (0.3 mm clearance)
to locate it. No print pauses or supports are needed.

To get the polarity right without thinking about it:
1. Press the 4 base magnets in, all the same way up.
2. Let a second magnet snap onto each one (they self-orient to attract).
3. Put a drop of CA glue in each lid recess if the press fit is loose,
   lower the lid straight down onto the stacked magnets and press: they
   go into the lid recesses in the correct orientation.

The walls are as thick as the magnets need (`WALL` is computed, 9.1 mm for
6 mm magnets), so the box grows outward; the SMA and USB openings get outside
recesses that bring the wall back to 2.4 mm in front of each port.

## Radio + Pi 3 B+ enclosure (`cad/pi_enclosure.py`)

One box, 230 x 82 x 27 mm, holding the radio board and a Raspberry Pi 3 B+
side by side, joined by a short straight USB cable inside:

- the radio is turned 90 degrees so its USB-C points straight at the Pi; the
  Pi is turned so its USB/Ethernet edge faces the radio, and a straight USB-C
  to USB-A cable runs straight across the 70 mm gap between them (a cable
  longer than ~15 mm between the plugs just bows sideways in the gap)
- both boards' port edges line up on the back wall: the radio's SMA, then the
  Pi's micro-USB power, HDMI and audio; the Pi's SD card is in the right wall
- Ethernet and the other USB ports are inside (use the Pi's WiFi)
- the antenna's bias-T screws onto the SMA outside and is powered from the
  Pi: its fixed USB cable comes in through a hole in the back wall over the
  gap, split between base and lid so the plug never has to pass through (lay
  the cable in the base before closing), is held by a zip-tie anchor just
  inside, and plugs into the Pi's back USB stack; the radio uses the front
  stack. Set `BIAST_CABLE_D` to your cable's diameter
- 7 x M2.5 x 12 mm screws from below: four through the Pi's mounting holes
  (clamping the Pi between its standoffs and the lid), three into posts at the
  front-left and the front and back of the gap; the SMA nut holds the
  back-left corner
- vent slots in the floor and lid, centred over the Pi's SoC
- the radio board (no mounting holes) is clamped at its corners by the lid and
  stuck down with 4 x 10 mm squares of 1 mm double-sided foam tape on raised
  platforms (`PAD_T`, `PAD_PTS`); the Pi is screwed, no tape

**Hardware** (also engraved on the base underside):

| Qty | Part | Where |
|---|---|---|
| 7 | M2.5 x 12 mm screw (socket or pan head, head <= 5 mm dia; 10-20 mm also fit) | from below: 4 through the Pi's mounting holes into the lid, 3 into the posts; heads sit in 5.5 x 3 mm counterbores, threads cut into 2.2 mm pilot holes in the lid |
| 4 | 8 mm stick-on rubber feet | 0.6 mm pockets on the underside |
| 4 | 10 x 10 mm squares of 1 mm double-sided foam tape | platforms under the radio board |
| 1 | small zip tie (<= 3.6 mm wide) | bias-T cable anchor inside the back wall |
| 1 | USB-C to USB-A cable, straight plugs | radio to the Pi's front USB stack |

**Bed fit:** at 230 mm it is longer than a 220 x 220 mm bed, and it doesn't fit
diagonally either (needs ~221 mm). Shorten `CABLE_SLACK` or the plug lengths
to bring it under 220 mm, or print on a larger bed.

```sh
.venv/bin/python cad/pi_enclosure.py out/pi ../radio-project/radio-project.step
```

It prints fit checks against both boards and the reserved cable space, and
writes `out/pi/print/pi_{base,lid}.{stl,3mf,step}` (bed-oriented) plus
`out/pi/pi_enclosure_assembly.step` and, for viewing, `radio_placed.step`,
`pi3bplus_placed.step` and `cable_keepout.step`. The gap is
`USB_C_PLUG + CABLE_SLACK + USB_A_PLUG` plus the ports' offsets from the board
edges: measure your cable's plugs and set them, and the box resizes. Pi
underside parts (SD card, GPIO pin tails) come from the official drawing,
since `pi3bplus.step` models only the top.

## Common tweaks

All dimensions are in mm, at the top of `cad/enclosure.py`:

| Parameter | Default | Change it when |
|---|---|---|
| `LIP_CLR` | 0.3 | lid is loose on the base → 0.2 |
| `SMA_CLR` / `SMA_FLANGE_CLR` | 0.45 / 0.5 | SMA connector is tight in its hole |
| `SMA_PROUD` | 2.0 | measure how far your soldered SMA's square flange sits past the board edge; the case fits up to ~0.3 mm beyond this |
| `MAGNET_D`, `MAGNET_T`, `MAGNET_FIT` | 6 / 2 / 0.2 | different magnets, or the press fit is too tight/loose; the walls resize automatically |
| `MAGNET_LAYOUT` | `"corners"` | `"sides"` for 2 magnets per half, mid-span left/right |
| `R_OUT` | 3.0 | rounder corners (keep ≤ 3.9 with corner magnets; the build warns if a wall gets thin) |
| `WALL_MIN`, `TOP`, `FLOOR` | 2.4 / 2.0 / 2.0 | stiffer or lighter shell (`WALL` itself follows the magnet size) |
| `USB_W`, `USB_H` | 12.6 / 7.0 | your USB-C plug housing doesn't fit |

Lid text is set near the end of the lid section (`engrave_top(...)` lines).
The board is built without the rotary encoder: the lid has no shaft opening,
and the encoder in `radio-project.step` will show as an overlap with the lid.

After any change, rebuild and look at the assembly in FreeCAD before printing.

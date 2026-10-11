# meche — 3D-printed enclosure

Two-piece enclosure (base + lid) and tuning knob for the Tayloe SDR board,
generated from code. The board drops into the base, the lid closes over it at
the board's top surface, and four M2.5 screws from below hold it together.

```
cad/enclosure.py   the design (CadQuery) — edit this
cad/to_fcstd.py    packs board + parts into a FreeCAD file for viewing
out/               generated files (git-ignored, rebuild any time)
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
| `out/print/{base,lid,knob}.{stl,3mf,step}` | **Send these to the printer.** Already oriented flat on the bed at Z = 0 |
| `out/enclosure_{base,lid}.step`, `out/knob.step` | Parts in board coordinates, for CAD |
| `out/tayloe_sdr_enclosure_assembly.step` | Board + all parts assembled |
| `out/enclosure.FCStd` | Same assembly for FreeCAD; lid 70 % transparent |

The FreeCAD file contains plain solids with no feature history — make changes
in `enclosure.py`, not in FreeCAD.

## Printing

| Part | Orientation | Supports |
|---|---|---|
| base | bottom down | none |
| lid | flipped, top face down (engraving on the bed) | none |
| knob | flat bottom down, shaft bore facing the bed | none |

PETG or PLA, 0.2 mm layers, 3 walls. Prefer `lid.step` if your slicer takes
STEP (PrusaSlicer, Bambu Studio, OrcaSlicer): the lid STL has ~100 tiny
self-intersections inside the engraved letters. Slicers repair them
automatically, but STEP avoids them.

Hardware: 4 × M2.5 × 8 mm screws (self-tapping into the lid), 4 × 8 mm
stick-on rubber feet (they sit in 0.6 mm pockets on the bottom).

## Common tweaks

All dimensions are in mm, at the top of `cad/enclosure.py`:

| Parameter | Default | Change it when |
|---|---|---|
| `LIP_CLR` | 0.15 | lid won't press onto the base → 0.2–0.3 |
| `SMA_CLR` / `SMA_FLANGE_CLR` | 0.45 / 0.5 | SMA connector is tight in its hole |
| `SCREW_PILOT` | 2.2 | switching to heat-set inserts (use the insert's hole size) |
| `KNOB_D`, `KNOB_H` | 20 / 12 | different knob size |
| `WALL`, `TOP`, `FLOOR` | 2.4 / 2.0 / 2.0 | stiffer or lighter shell |
| `USB_W`, `USB_H` | 12.6 / 7.0 | your USB-C plug housing doesn't fit |

Lid text is set near the end of the lid section (`engrave_top(...)` lines).
The knob bore assumes a 6 mm D-shaft with the flat at 4.5 mm — check your
encoder's datasheet.

After any change, rebuild and look at the assembly in FreeCAD before printing.

# meche: 3D-printed enclosure

![Radio + Pi 3 B+ enclosure, lid see-through](screen-captures/initial-enclosure.png)

## Goal

One printed box that holds the Tayloe SDR receiver board and a Raspberry Pi 3 B+ side by side, so the radio and the
Pi that runs it (GNU Radio, the WebSDR) sit together as a single unit:

- the radio's USB-C goes straight across to the Pi on a short cable inside the box
- the outside connections (the radio's SMA antenna port, the Pi's power, HDMI, audio and SD card) come out through the walls
- the antenna's bias-T is powered from the Pi, its cable coming in through the back wall
- vent slots over the Pi's SoC
- the box must fit a 220 x 220 mm print bed

The next revision should be waterproof: a gasket at the base/lid joint, a sealed bulkhead SMA, cable glands instead of
the open port cut-outs, and a breathable vent membrane (see the TODO in `code/CLAUDE.md`).

## How it's built

The enclosure is generated from code with CadQuery, by `cad/pi_enclosure.py` on the `pi-enclosure` branch (not on
`main` yet). It is driven by `../radio-project/radio-project.step`, exported from KiCad, so re-export it and rebuild when the
board changes. Run from `meche/` with its own Python 3.12 environment (CadQuery doesn't support 3.14):

```sh
.venv/bin/python cad/pi_enclosure.py out/pi ../radio-project/radio-project.step
```

Each build prints fit checks (overlaps with both boards, the cable and bias-T routes, whether it fits the print bed).
Read them before you export. Print files land in `out/pi/print/`. The `README.md` on `pi-enclosure` has the full details:
hardware list, screws, cable lengths and parameters.

The current build is 230 x 84 x 27 mm, which is still too long for the 220 mm bed.

## FreeCAD MCP

We view and inspect the models in FreeCAD through the **FreeCAD MCP** server, so Claude Code can open the assembly,
colour the parts, make the lid see-through, check the fit and take screenshots like the one above. Drive FreeCAD only
through the MCP: `freecadcmd` saves no colours or visibility.

# Mechanical enclosure TODOs

Open work for the radio + Pi 3 B+ enclosure (`cad/pi_enclosure.py`, branch `pi-enclosure`).

## Design review feedback

> "It does the basics well! Missing some ribs, creativity, and I'd recommend better mating than the screw holes."
> "Basically skeletal structure — you don't need it for simple design especially 3D printed but it brings the
> whole look together."

- [ ] **Better mating than screws.** Proposed:
  - The existing rim lip/groove locates the lid.
  - Cantilever snap clips on the two long walls: a tab on the base hooks a window in the lid. Tool-less, printable
    without supports, invisible from outside.
  - The Pi screws to its own base standoffs with M2.5 heat-set inserts, so it no longer depends on the lid.
  - The radio stays clamped by the lid pins (held by the snaps) plus its adhesive pads.
  - Variants: add two hidden screws from below as a transport lock; or flush 6 × 2 mm magnets (walls thicken,
    box grows ~13 mm).
- [ ] **Ribs / skeletal structure:**
  - Lid stiffening grid on the underside, tied to the clamp pins and posts. It must clear both boards and both cable
    keep-outs; the Pi USB stack is only 1.4 mm under the ceiling.
  - Floor ribs between the posts and pad platforms.
  - Optional, and breaks the "plain outside" rule, so decide first: vertical heatsink-style fins on the front wall,
    doubling as vents over the Pi.
- [ ] **Creativity / styling:**
  - Speaker-grille or waterfall-pattern vents over the Pi instead of plain slots.
  - Recessed, framed label panel for "TAYLOE SDR / MAHJOUB'S STUDIO".
  - Chamfer or step at the parting line, so a two-colour print (lid/base) looks deliberate.

## Blocking printing

- [ ] **Fit the 220 × 220 mm bed.** The box is 230.0 × 83.6 × 26.9 mm and doesn't fit straight or diagonally (needs
  ~221 mm). The length is the cable gap (69.6 mm). Options:
  - Measure the real cable and set `USB_C_PLUG` / `USB_A_PLUG` / `CABLE_SLACK`. About 15 mm shorter is enough.
  - Use a right-angle USB-C/USB-A cable: ~190 mm box.
  - Go back to the 203 × 119 mm channel layout (commit `188d459`); the bias-T entry needs redoing there.
  - Print on a bigger bed or through a service.
- [ ] **Measure and set:**
  - `SMA_PROUD`: how far the hand-soldered SMA flange sits past the board edge (assumed 2.0 mm).
  - `BIAST_CABLE_D`: the bias-T power cable's diameter (assumed 4.0 mm).

## Power / electrical

- [ ] Check the MLA-30+ bias-T current draw against the Pi's ~1.2 A shared USB budget (the radio uses it too).
- [ ] Next radio PCB revision:
  - 4 × M2.5 mounting holes (~3.5 mm from the corners) to replace the clamp pins and adhesive pads.
  - Optionally an on-board bias-T: RF choke from +5 V onto the antenna side of C20, with a jumper. This removes the
    external injector and its cable entry.

## Tooling

- [ ] `cad/push_gdrive.sh` calls `cad/to_fcstd.py`, which launches FreeCAD outside the MCP. Make it copy the CadQuery
  outputs only, and build the `.FCStd` through the FreeCAD MCP. Extend it to upload `out/pi/` too.
- [ ] Commit the current `pi-enclosure` work: bias-T cable entry, tie anchor, thicker back wall, `CLAUDE.md`, this
  file.

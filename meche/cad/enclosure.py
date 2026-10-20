"""Two-piece 3D-printable enclosure for the Tayloe SDR board (radio-project.step).

Board frame (from the KiCad STEP): board occupies X 0..70, Y 0..70, Z 0..1.42.
Parting line is the board's top surface (Z = 1.42): the board drops into the
base and the lid snaps on with neodymium disc magnets pressed into flush
recesses in both rims. A lip on the base rim fits a groove in the lid to
locate it. The rim is as thick as the magnets need, so the walls grow outward
and the outside stays a plain rounded square. The board has no mounting holes,
so it is clamped at its four corners between posts in the base and pins in
the lid.
"""
import sys
import cadquery as cq

OUT = sys.argv[1]

# ---------------- board-derived geometry (measured from the STEP) -------------
BW, BL, BT = 70.0, 70.0, 1.42          # board size / thickness
SPLIT = BT                             # parting plane = board top
SMA_Y, SMA_Z = 14.17, 2.00             # SMA barrel axis (flange centre)
SMA_THREAD = 6.35                      # 1/4-36 thread OD
SMA_FLANGE = 6.35                      # square flange, sits 0.43 mm proud of board edge
SMA_CLR = 0.45                         # radial clearance, barrel hole
SMA_FLANGE_CLR = 0.5                   # per-side clearance, flange pocket
SMA_D = SMA_THREAD + 2 * SMA_CLR
USB_X, USB_Z = 34.72, 3.81             # USB-C receptacle centre
USB_W, USB_H = 12.6, 7.0               # opening sized for typical plug overmold
ENC_X, ENC_Y = 60.47, 49.87            # encoder shaft axis
SHAFT_TOP = 16.5

# ---------------- magnets (flush, press-fit in both rims) ---------------------
MAGNET_D, MAGNET_T = 6.0, 2.0  # neodymium disc
MAGNET_FIT = 0.2               # added to the diameter for a press fit
MAGNET_LAYOUT = "corners"      # "corners" (4 per half) or "sides" (2, mid-span left/right)
RIM_MARGIN = 0.8               # min plastic between a pocket and any surface
POCKET_D = MAGNET_D + MAGNET_FIT
POCKET_DEPTH = MAGNET_T        # magnets sit flush with the mating face

# ---------------- enclosure parameters ----------------------------------------
GAP = 0.3          # board-to-wall clearance
FLOOR = 2.0
FLOOR_TOP = -3.0   # encoder leads reach Z = -2.09
CEIL = 8.0         # inner ceiling (encoder body top = 7.10)
TOP = 2.0
LIP_W, LIP_H, LIP_CLR = 1.0, 1.5, 0.3   # locating lip on the base, groove in the lid
R_OUT = 3.0        # outer vertical-edge fillet
WALL_MIN = 2.4
# the rim band between the lid groove and the outside must hold a pocket
WALL = max(WALL_MIN, LIP_W + LIP_CLR + POCKET_D + 2 * RIM_MARGIN)
PORT_WALL = 2.4    # wall left in front of the SMA / USB, via outside recesses
SMA_RECESS_D = 12.0                    # room for the antenna plug's coupling nut
USB_RECESS_W, USB_RECESS_H = 16.0, 10.0

cx0, cy0 = -GAP, -GAP
cw, cl = BW + 2 * GAP, BL + 2 * GAP
ox0, oy0 = cx0 - WALL, cy0 - WALL
ow, ol = cw + 2 * WALL, cl + 2 * WALL
CX, CY = BW / 2, BL / 2

z_bot = FLOOR_TOP - FLOOR
z_top = CEIL + TOP

# magnet centres: in the rim band, RIM_MARGIN clear of the lid groove
_m = LIP_W + LIP_CLR + RIM_MARGIN + POCKET_D / 2      # inward from the cavity edge
if MAGNET_LAYOUT == "corners":
    mag_pts = [(cx0 - _m, cy0 - _m), (cx0 + cw + _m, cy0 - _m),
               (cx0 - _m, cy0 + cl + _m), (cx0 + cw + _m, cy0 + cl + _m)]
elif MAGNET_LAYOUT == "sides":
    mag_pts = [(cx0 - _m, CY), (cx0 + cw + _m, CY)]
else:
    raise ValueError(MAGNET_LAYOUT)

def rbox(x0, y0, w, l, z0, z1, r=0.0):
    wp = cq.Workplane("XY").workplane(offset=z0).center(x0 + w / 2, y0 + l / 2)
    s = wp.rect(w, l).extrude(z1 - z0)
    if r > 0:
        s = s.edges("|Z").fillet(r)
    return s

def lip_ring(clr):
    outer = rbox(cx0 - LIP_W - clr, cy0 - LIP_W - clr,
                 cw + 2 * (LIP_W + clr), cl + 2 * (LIP_W + clr),
                 SPLIT, SPLIT + LIP_H + clr, 0.8)
    inner = rbox(cx0 - clr, cy0 - clr, cw + 2 * clr, cl + 2 * clr,
                 SPLIT - 1, SPLIT + LIP_H + 2, 0.3)
    return outer.cut(inner)

def magnet_pockets(z0):
    return (cq.Workplane("XY").workplane(offset=z0).pushPoints(mag_pts)
            .circle(POCKET_D / 2).extrude(POCKET_DEPTH))

# side cut-outs (shared by both halves)
sma_cut = (cq.Workplane("YZ").workplane(offset=ox0 - 1).center(SMA_Y, SMA_Z)
           .circle(SMA_D / 2).extrude(WALL + LIP_W + 3))
# relief for the square flange where it overhangs the board edge
_fh = SMA_FLANGE / 2 + SMA_FLANGE_CLR
sma_pocket = rbox(-1.0, SMA_Y - _fh, 1.2, 2 * _fh, SMA_Z - _fh, SMA_Z + _fh)
usb_cut = (cq.Workplane("XZ").workplane(offset=-(BL + GAP - 1.5))
           .center(USB_X, USB_Z).rect(USB_W, USB_H).extrude(-(WALL + LIP_W + 4))
           .edges("|Y").fillet(1.5))
# outside recesses thin the thick rim back to PORT_WALL in front of each port,
# so the SMA thread still sticks out and a USB plug reaches its receptacle
sma_recess = (cq.Workplane("YZ").workplane(offset=ox0 - 1).center(SMA_Y, SMA_Z)
              .circle(SMA_RECESS_D / 2).extrude(WALL - PORT_WALL + 1))
usb_recess = (cq.Workplane("XZ").workplane(offset=-(oy0 + ol + 1))
              .center(USB_X, USB_Z).rect(USB_RECESS_W, USB_RECESS_H)
              .extrude(WALL - PORT_WALL + 1).edges("|Y").fillet(2.0))
ports = sma_cut.union(usb_cut).union(sma_pocket).union(sma_recess).union(usb_recess)

# ---------------- base ---------------------------------------------------------
base = rbox(ox0, oy0, ow, ol, z_bot, SPLIT, R_OUT)
base = base.cut(rbox(cx0, cy0, cw, cl, FLOOR_TOP, SPLIT + 1, 0.3))
base = base.union(lip_ring(0.0))
# corner posts: board rests on these (board underside Z = 0)
POST = 4.0
for (px, py) in [(0, 0), (BW - POST, 0), (0, BL - POST), (BW - POST, BL - POST)]:
    base = base.union(rbox(px, py, POST, POST, FLOOR_TOP - 0.1, 0.0))
# mid-span posts on front/back edges stop the board flexing when the knob is pushed
for (px, py) in [(BW / 2 - 2, 0), (BW / 2 - 2, BL - 3)]:
    base = base.union(rbox(px, py, 4.0, 3.0, FLOOR_TOP - 0.1, 0.0))
base = base.cut(ports)
# shallow pockets for 8 mm stick-on rubber feet
feet = [(8, 8), (BW - 8, 8), (8, BL - 8), (BW - 8, BL - 8)]
base = base.cut(cq.Workplane("XY").workplane(offset=z_bot - 1).pushPoints(feet)
                .circle(4.3).extrude(1.6))

# ---------------- lid ----------------------------------------------------------
lid = rbox(ox0, oy0, ow, ol, SPLIT, z_top, R_OUT)
lid = lid.cut(rbox(cx0, cy0, cw, cl, SPLIT - 1, CEIL, 0.3))
lid = lid.cut(rbox(cx0 - LIP_W - LIP_CLR, cy0 - LIP_W - LIP_CLR,
                   cw + 2 * (LIP_W + LIP_CLR), cl + 2 * (LIP_W + LIP_CLR),
                   SPLIT - 1, SPLIT + LIP_H + LIP_CLR, 0.8))
# clamp pins: press the board corners down onto the base posts
PIN = 3.0
for (px, py) in [(0.4, 0.4), (BW - PIN - 0.4, 0.4), (0.4, BL - PIN - 0.4),
                 (BW - PIN - 0.4, BL - PIN - 0.4)]:
    lid = lid.union(rbox(px, py, PIN, PIN, SPLIT + 0.05, CEIL + 0.1))
lid = lid.cut(ports)
# encoder shaft hole (top stays flat so the lid prints face-down)
lid = lid.cut(cq.Workplane("XY").workplane(offset=CEIL - 1).center(ENC_X, ENC_Y)
              .circle(3.6).extrude(TOP + 3))

# engraved labels (0.6 mm deep)
def engrave_top(body, text, x, y, size):
    t = (cq.Workplane("XY").workplane(offset=z_top - 0.6).center(x, y)
         .text(text, size, 1.0, kind="bold", halign="center", valign="center"))
    return body.cut(t)

lid = engrave_top(lid, "TAYLOE SDR", 26, 20, 6.0)
lid = engrave_top(lid, "MAHJOUB'S STUDIO", 26, 12, 3.2)
lid = engrave_top(lid, "TUNE", ENC_X, ENC_Y - 13, 3.2)
def engrave_side(body, text, origin, xdir, normal):
    pl = cq.Plane(origin=origin, xDir=xdir, normal=normal)
    t = cq.Workplane(pl).text(text, 3.2, -0.6, kind="bold",
                              halign="center", valign="center")
    return body.cut(t)

lid = engrave_side(lid, "ANT", (ox0, SMA_Y + 12, 5.7), (0, -1, 0), (-1, 0, 0))
lid = engrave_side(lid, "USB", (USB_X - 15, oy0 + ol, 5.7), (-1, 0, 0), (0, 1, 0))

# ---------------- magnet recesses in both mating faces ------------------------
base_solid, lid_solid = base, lid            # kept for the wall check
base_pk = magnet_pockets(SPLIT - POCKET_DEPTH)
lid_pk = magnet_pockets(SPLIT)
base = base.cut(base_pk)
lid = lid.cut(lid_pk)

def min_wall(solid, pockets):
    """Thinnest side wall around any pocket (or between two pockets)."""
    bb, pb = solid.val().BoundingBox(), pockets.val().BoundingBox()
    band = (cq.Workplane("XY").box(bb.xlen + 20, bb.ylen + 20, pb.zlen)
            .translate((bb.center.x, bb.center.y, pb.center.z)))
    outside = band.cut(solid)
    ps = pockets.solids().vals()
    walls = [outside.val().distance(p) for p in ps]
    walls += [a.distance(b) for i, a in enumerate(ps) for b in ps[i + 1:]]
    return min(walls)

print(f"magnets: {len(mag_pts)} per half ({MAGNET_LAYOUT}), {MAGNET_D} x {MAGNET_T} mm; "
      f"recess {POCKET_D:.2f} dia x {POCKET_DEPTH:.2f} deep (flush); wall {WALL:.2f} mm")
for name, solid, pk in (("base", base_solid, base_pk), ("lid", lid_solid, lid_pk)):
    w = min_wall(solid, pk)
    print(f"{name}: min wall around recesses {w:.2f} mm"
          + ("" if w >= RIM_MARGIN - 1e-6 else f"  WARNING: < {RIM_MARGIN} mm"))

# ---------------- knob (6 mm D-shaft, flat at 4.5 mm) --------------------------
KNOB_D, KNOB_H = 20.0, 12.0
kz0 = z_top + 1.4                           # clearance above the lid
knob = (cq.Workplane("XY").workplane(offset=kz0).center(ENC_X, ENC_Y)
        .polygon(30, KNOB_D).extrude(KNOB_H).edges(">Z").fillet(1.5))
bore_depth = min(SHAFT_TOP - kz0 + 0.3, KNOB_H - 2.5)
bore = (cq.Workplane("XY").workplane(offset=kz0 - 0.1).center(ENC_X, ENC_Y)
        .circle(3.05).extrude(bore_depth + 0.1))
flat_keep = (cq.Workplane("XY").workplane(offset=kz0 - 0.2)
             .center(ENC_X, ENC_Y + 4.55 - 3.05 - 5.0).rect(14, 10)
             .extrude(bore_depth + 1))
knob = knob.cut(bore.intersect(flat_keep))
knob = knob.cut(cq.Workplane("XY").workplane(offset=kz0 + KNOB_H - 0.8)
                .center(ENC_X, ENC_Y + KNOB_D / 2 - 3.5).rect(1.2, 5).extrude(2))

# ---------------- export -------------------------------------------------------
cq.exporters.export(base, f"{OUT}/enclosure_base.step")
cq.exporters.export(lid, f"{OUT}/enclosure_lid.step")
cq.exporters.export(knob, f"{OUT}/knob.step")
for name, part in (("enclosure_base", base), ("enclosure_lid", lid), ("knob", knob)):
    cq.exporters.export(part, f"{OUT}/{name}.stl", tolerance=0.02, angularTolerance=0.1)

# print-ready copies: each part on its flat face, resting on Z = 0
import os
os.makedirs(f"{OUT}/print", exist_ok=True)
# exact offsets rather than a bounding box, which can be slightly loose
def on_bed(part, bottom, flip=False):
    if flip:
        part = part.rotate((0, 0, 0), (1, 0, 0), 180)
        bottom = -bottom
    return part.translate((0, 0, -bottom))
for name, part in (("base", on_bed(base, z_bot)), ("lid", on_bed(lid, z_top, flip=True)),
                   ("knob", on_bed(knob, kz0))):
    # finer meshes make the engraved lettering self-intersect more, not less
    cq.exporters.export(part, f"{OUT}/print/{name}.stl", tolerance=0.02, angularTolerance=0.1)
    cq.exporters.export(part, f"{OUT}/print/{name}.3mf", tolerance=0.02, angularTolerance=0.1)
    cq.exporters.export(part, f"{OUT}/print/{name}.step")   # slicers that take STEP mesh it cleanly

board = cq.importers.importStep(sys.argv[2])
asm = cq.Assembly(name="tayloe_sdr_enclosure")
asm.add(board, name="pcb")
asm.add(base, name="base", color=cq.Color(0.20, 0.22, 0.25))
asm.add(lid, name="lid", color=cq.Color(0.20, 0.22, 0.25, 0.35))
asm.add(knob, name="knob", color=cq.Color(0.85, 0.35, 0.10))
asm.save(f"{OUT}/tayloe_sdr_enclosure_assembly.step")

bb = base.union(lid).val().BoundingBox()
print(f"outer {bb.xlen:.1f} x {bb.ylen:.1f} x {bb.zlen:.1f} mm")
print("knob bore depth", round(bore_depth, 2), "kz0", kz0)

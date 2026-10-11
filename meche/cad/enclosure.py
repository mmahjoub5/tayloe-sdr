"""Two-piece 3D-printable enclosure for the Tayloe SDR board (radio-project.step).

Board frame (from the KiCad STEP): board occupies X 0..70, Y 0..70, Z 0..1.42.
Parting line is the board's top surface (Z = 1.42): the board drops into the
base, the lid closes over it, and four M2.5 screws from below hold it together.
The board has no mounting holes, so it is clamped at its four corners between
posts in the base and pins in the lid.
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

# ---------------- enclosure parameters ----------------------------------------
GAP = 0.3          # board-to-wall clearance
WALL = 2.4
FLOOR = 2.0
FLOOR_TOP = -3.0   # encoder leads reach Z = -2.09
CEIL = 8.0         # inner ceiling (encoder body top = 7.10)
TOP = 2.0
LIP_W, LIP_H, LIP_CLR = 1.0, 1.5, 0.15
R_OUT = 3.0
BOSS_R, BOSS_OFF = 3.4, 3.4
SCREW_CLR, SCREW_PILOT = 2.9, 2.2
CB_D, CB_DEPTH = 5.5, 3.0

cx0, cy0 = -GAP, -GAP
cw, cl = BW + 2 * GAP, BL + 2 * GAP
ox0, oy0 = cx0 - WALL, cy0 - WALL
ow, ol = cw + 2 * WALL, cl + 2 * WALL
CX, CY = BW / 2, BL / 2

z_bot = FLOOR_TOP - FLOOR
z_top = CEIL + TOP

def rbox(x0, y0, w, l, z0, z1, r=0.0):
    wp = cq.Workplane("XY").workplane(offset=z0).center(x0 + w / 2, y0 + l / 2)
    s = wp.rect(w, l).extrude(z1 - z0)
    if r > 0:
        s = s.edges("|Z").fillet(r)
    return s

boss_pts = [(-BOSS_OFF, -BOSS_OFF), (BW + BOSS_OFF, -BOSS_OFF),
            (-BOSS_OFF, BL + BOSS_OFF), (BW + BOSS_OFF, BL + BOSS_OFF)]

def bosses(z0, z1):
    return (cq.Workplane("XY").workplane(offset=z0).pushPoints(boss_pts)
            .circle(BOSS_R).extrude(z1 - z0))

def lip_ring(clr):
    outer = rbox(cx0 - LIP_W - clr, cy0 - LIP_W - clr,
                 cw + 2 * (LIP_W + clr), cl + 2 * (LIP_W + clr),
                 SPLIT, SPLIT + LIP_H + clr, 0.8)
    inner = rbox(cx0 - clr, cy0 - clr, cw + 2 * clr, cl + 2 * clr,
                 SPLIT - 1, SPLIT + LIP_H + 2, 0.3)
    return outer.cut(inner)

# side cut-outs (shared by both halves)
sma_cut = (cq.Workplane("YZ").workplane(offset=ox0 - 1).center(SMA_Y, SMA_Z)
           .circle(SMA_D / 2).extrude(WALL + LIP_W + 3))
# relief for the square flange where it overhangs the board edge
_fh = SMA_FLANGE / 2 + SMA_FLANGE_CLR
sma_pocket = rbox(-1.0, SMA_Y - _fh, 1.2, 2 * _fh, SMA_Z - _fh, SMA_Z + _fh)
usb_cut = (cq.Workplane("XZ").workplane(offset=-(BL + GAP - 1.5))
           .center(USB_X, USB_Z).rect(USB_W, USB_H).extrude(-(WALL + LIP_W + 4))
           .edges("|Y").fillet(1.5))

# ---------------- base ---------------------------------------------------------
base = rbox(ox0, oy0, ow, ol, z_bot, SPLIT, R_OUT).union(bosses(z_bot, SPLIT))
base = base.cut(rbox(cx0, cy0, cw, cl, FLOOR_TOP, SPLIT + 1, 0.3))
base = base.union(lip_ring(0.0))
# corner posts: board rests on these (board underside Z = 0)
POST = 4.0
for (px, py) in [(0, 0), (BW - POST, 0), (0, BL - POST), (BW - POST, BL - POST)]:
    base = base.union(rbox(px, py, POST, POST, FLOOR_TOP - 0.1, 0.0))
# mid-span posts on front/back edges stop the board flexing when the knob is pushed
for (px, py) in [(BW / 2 - 2, 0), (BW / 2 - 2, BL - 3)]:
    base = base.union(rbox(px, py, 4.0, 3.0, FLOOR_TOP - 0.1, 0.0))
base = base.cut(sma_cut).cut(usb_cut).cut(sma_pocket)
# screw holes + counterbores from below
base = base.cut(cq.Workplane("XY").workplane(offset=z_bot - 1).pushPoints(boss_pts)
                .circle(SCREW_CLR / 2).extrude(SPLIT - z_bot + 2))
base = base.cut(cq.Workplane("XY").workplane(offset=z_bot - 1).pushPoints(boss_pts)
                .circle(CB_D / 2).extrude(CB_DEPTH + 1))
# shallow pockets for 8 mm stick-on rubber feet
feet = [(8, 8), (BW - 8, 8), (8, BL - 8), (BW - 8, BL - 8)]
base = base.cut(cq.Workplane("XY").workplane(offset=z_bot - 1).pushPoints(feet)
                .circle(4.3).extrude(1.6))

# ---------------- lid ----------------------------------------------------------
lid = rbox(ox0, oy0, ow, ol, SPLIT, z_top, R_OUT).union(bosses(SPLIT, z_top))
lid = lid.cut(rbox(cx0, cy0, cw, cl, SPLIT - 1, CEIL, 0.3))
lid = lid.cut(rbox(cx0 - LIP_W - LIP_CLR, cy0 - LIP_W - LIP_CLR,
                   cw + 2 * (LIP_W + LIP_CLR), cl + 2 * (LIP_W + LIP_CLR),
                   SPLIT - 1, SPLIT + LIP_H + LIP_CLR, 0.8))
# clamp pins: press the board corners down onto the base posts
PIN = 3.0
for (px, py) in [(0.4, 0.4), (BW - PIN - 0.4, 0.4), (0.4, BL - PIN - 0.4),
                 (BW - PIN - 0.4, BL - PIN - 0.4)]:
    lid = lid.union(rbox(px, py, PIN, PIN, SPLIT + 0.05, CEIL + 0.1))
lid = lid.cut(sma_cut).cut(usb_cut).cut(sma_pocket)
# encoder shaft hole (top stays flat so the lid prints face-down)
lid = lid.cut(cq.Workplane("XY").workplane(offset=CEIL - 1).center(ENC_X, ENC_Y)
              .circle(3.6).extrude(TOP + 3))
# screw pilots
lid = lid.cut(cq.Workplane("XY").workplane(offset=SPLIT - 1).pushPoints(boss_pts)
              .circle(SCREW_PILOT / 2).extrude(CEIL - SPLIT + 1.5))

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
def on_bed(part, flip=False):
    if flip:
        part = part.rotate((0, 0, 0), (1, 0, 0), 180)
    return part.translate((0, 0, -part.val().BoundingBox().zmin))
for name, part in (("base", on_bed(base)), ("lid", on_bed(lid, flip=True)),
                   ("knob", on_bed(knob))):
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

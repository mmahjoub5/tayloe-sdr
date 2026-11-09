"""Combined enclosure: Tayloe SDR board + Raspberry Pi 3 B+ side by side.

Usage: python cad/pi_enclosure.py <out dir> <radio-project.step>

Global frame: X along the box, Y from front to back, Z up. The radio board is
turned 90 degrees clockwise from its own frame and sits at the left (global
X 0..70, Y 0..70), so its USB-C points right, straight at the Pi, and its SMA
leaves through the back wall. The Pi sits to the right, turned 180 degrees so
its USB/Ethernet edge faces the radio; a short straight USB-C to USB-A cable
runs straight across the gap. Both boards' port edges line up on the back wall
(SMA, then the Pi's power/HDMI/audio); the Pi's SD slot is in the right wall.

Parting line is the radio board's top (Z = 1.42). Seven M2.5 x 12 screws go
in from below: four through the Pi's own mounting holes (clamping the Pi
between its standoffs and the lid) and three into posts (front-left, and front
and back of the gap between the boards); the SMA nut holds the back-left
corner. The antenna's bias-T screws onto the SMA outside and takes 5 V from a
spare Pi USB port: its fixed cable enters through a hole split between base
and lid (laid in before closing, so the plug never passes the wall) and is
held by a zip-tie anchor. Fit checks use the Pi 3 B+ model in rpi-step/pi3bplus.step (GrabCAD,
matches the official drawing to within ~1 mm). That model has nothing under
the board, so the SD card and GPIO pin tails come from the drawing.
"""
import os
import sys
import cadquery as cq

OUT = sys.argv[1]
os.makedirs(f"{OUT}/print", exist_ok=True)

# ---------------- radio board (its own frame, measured from the STEP) ----------
BW, BL, BT = 70.0, 70.0, 1.42
SPLIT = BT                             # parting plane = radio board top
SMA_Y, SMA_Z = 14.17, 2.00             # SMA on the radio's left edge (radio frame)
SMA_THREAD, SMA_FLANGE = 6.35, 6.35
SMA_CLR, SMA_FLANGE_CLR = 0.45, 0.5
SMA_PROUD = 2.0                        # hand-soldered flange may sit this far out
SMA_FLANGE_GAP = 0.3
SMA_D = SMA_THREAD + 2 * SMA_CLR
RADIO_USBC_X, RADIO_USBC_Z = 34.72, 3.81   # USB-C on the radio's back edge
RADIO_USBC_MOUTH = 69.11                   # receptacle mouth (radio frame Y)

def radio_xy(x, y):
    """Radio-frame point -> global: turned 90 degrees clockwise, SMA edge at the back."""
    return y, BW - x

# ---------------- Raspberry Pi 3 B+ (official drawing; native frame) -----------
# native: board X 0..85, Y 0..56; USB/Ethernet edge at X = 85, power/HDMI/audio
# edge at Y = 0, SD card under the X = 0 edge. Z measured from the board bottom.
PI_W, PI_L, PI_T = 85.0, 56.0, 1.4
PI_HOLES = [(3.5, 3.5), (61.5, 3.5), (3.5, 52.5), (61.5, 52.5)]
PI_TOP = {                             # x0, x1, y0, y1, height above board top
    "usb_a": (69.4, 87.1, 22.45, 35.55, 16.0),
    "usb_b": (69.4, 87.1, 40.45, 53.55, 16.0),
    "ethernet": (65.6, 87.1, 2.3, 18.2, 13.5),
    "micro_usb": (6.6, 14.6, -1.3, 4.5, 3.0),
    "hdmi": (24.5, 39.5, -1.5, 10.0, 6.5),
    "audio": (50.5, 56.5, -2.5, 12.5, 6.0),
    "gpio": (7.1, 57.9, 49.9, 55.0, 8.5),
}
PI_UNDER = {                           # x0, x1, y0, y1, depth below board bottom
    "sd_card": (-2.4, 13.0, 22.0, 34.0, 1.5),   # card inserted
    "gpio_pins": (7.1, 57.9, 49.9, 55.0, 3.0),
}
PI_PORTS = {                           # back-wall openings: native x, height of centre
    "micro_usb": (10.6, 1.5),          # above board top, opening W x H for the plug
    "hdmi": (32.0, 3.25),
    "audio": (53.5, 3.0),
}
PORT_OPEN = {"micro_usb": (12.0, 8.0), "hdmi": (22.0, 12.0), "audio": (9.0, 9.0)}
PI_SD_Y = 28.0                         # native, centre of the SD slot
PI_USB_Y = 47.0                        # native, the USB stack the radio cable plugs into (front)
PI_USB_LOW_Z = 5.5                     # lower USB-A port centre above the board bottom
PI_SOC = (27.3, 27.6)                  # native, SoC centre (14.3 mm square, measured in the STEP)

# ---------------- bias-T power cable ---------------------------------------------
# The bias-T (screwed onto the SMA outside) has a fixed USB cable ending in a USB-A
# plug. It enters through the back wall over the gap, where it drops onto the
# floor clear of the radio board, and plugs into the lower port of the Pi USB
# stack the radio cable doesn't use.
BIAST_CABLE_D = 4.0   # cable outer diameter: measure yours
BIAST_HOLE_CLR = 0.3  # added to the diameter
BIAST_USB_Y = 29.0    # native Pi Y of the other USB stack (back): no crossing

# ---------------- layout -------------------------------------------------------
# internal USB cable: straight USB-C to straight USB-A, straight across the gap
USB_C_PLUG = 25.0    # straight USB-C plug, overmold + strain relief, beyond the port
USB_A_PLUG = 28.0    # straight USB-A plug, likewise
CABLE_SLACK = 15.0   # cable between the two plug tails; a longer cable bows sideways
PI_USB_PROUD = 2.5   # Pi USB/Ethernet stick out past its board edge (STEP model)
USBC_INSET = BL - RADIO_USBC_MOUTH                    # radio USB-C mouth sits inside its edge
CABLE_GAP = PI_USB_PROUD + USB_A_PLUG + CABLE_SLACK + USB_C_PLUG - USBC_INSET
FRONT = 7.0          # in front of the radio: room for the front screw posts
PI_STANDOFF = 4.5    # clears the GPIO pins and SD socket under the Pi
GAP = 0.3            # board-to-wall clearance

WALL = 2.4
SMA_PLATE = 1.6      # plastic left in front of the SMA flange pocket (nut and bias-T bear on it)
# the back wall carries the SMA, so it is thick enough for the flange pocket plus SMA_PLATE
WALL_BACK = max(WALL, SMA_PROUD + SMA_FLANGE_GAP - GAP + SMA_PLATE)
FLOOR = 2.0
FLOOR_TOP = -3.0
TOP = 2.0
LIP_W, LIP_H, LIP_CLR = 1.0, 1.5, 0.2
R_OUT = 3.0

PI_X0 = BW + CABLE_GAP                 # Pi footprint in the global frame
PI_Y0 = BW - PI_L                      # Pi's port edge in line with the radio's SMA edge
PI_Z0 = FLOOR_TOP + PI_STANDOFF        # Pi board underside
CEIL = PI_Z0 + PI_T + max(v[4] for v in PI_TOP.values()) + 1.0   # over the USB stack

cx0, cy0 = -GAP, -(GAP + FRONT)
cx1, cy1 = PI_X0 + PI_W + GAP, BW + GAP
ox0, oy0, ox1, oy1 = cx0 - WALL, cy0 - WALL, cx1 + WALL, cy1 + WALL_BACK
z_bot, z_top = FLOOR_TOP - FLOOR, CEIL + TOP

def pi_xy(x, y):
    """Native Pi coordinates -> global (the Pi is turned 180 degrees)."""
    return PI_X0 + (PI_W - x), PI_Y0 + (PI_L - y)

# ---------------- screws (M2.5 x 12 from below) -------------------------------
BOSS_R = 3.0
SCREW_CLR, SCREW_PILOT = 2.9, 2.2
CB_D, CB_DEPTH = 5.5, 3.0
pi_screws = [pi_xy(x, y) for (x, y) in PI_HOLES]
_gap_x = BW + CABLE_GAP / 2
frame_screws = [(3.5, cy0 + 3.5), (_gap_x, cy0 + 3.5), (_gap_x, cy1 - 3.5)]

# ---------------- helpers ------------------------------------------------------
def rbox(x0, y0, w, l, z0, z1, r=0.0):
    s = (cq.Workplane("XY").workplane(offset=z0).center(x0 + w / 2, y0 + l / 2)
         .rect(w, l).extrude(z1 - z0))
    return s.edges("|Z").fillet(r) if r > 0 else s

def box(x0, x1, y0, y1, z0, z1):
    return rbox(min(x0, x1), min(y0, y1), abs(x1 - x0), abs(y1 - y0), z0, z1)

def radio_box(x0, x1, y0, y1, z0, z1):
    """Box given in the radio's frame, placed in the global frame."""
    (gx0, gy0), (gx1, gy1) = radio_xy(x0, y0), radio_xy(x1, y1)
    return box(gx0, gx1, gy0, gy1, z0, z1)

def cyl(pts, r, z0, z1):
    return cq.Workplane("XY").workplane(offset=z0).pushPoints(pts).circle(r).extrude(z1 - z0)

def lip_ring(clr):
    outer = rbox(cx0 - LIP_W - clr, cy0 - LIP_W - clr, cx1 - cx0 + 2 * (LIP_W + clr),
                 cy1 - cy0 + 2 * (LIP_W + clr), SPLIT, SPLIT + LIP_H + clr, 0.8)
    inner = rbox(cx0 - clr, cy0 - clr, cx1 - cx0 + 2 * clr, cy1 - cy0 + 2 * clr,
                 SPLIT - 1, SPLIT + LIP_H + 2, 0.3)
    return outer.cut(inner)

# ---------------- openings -----------------------------------------------------
_sma_x, _ = radio_xy(0, SMA_Y)
sma_cut = cq.Workplane("XY").add(cq.Solid.makeCylinder(
    SMA_D / 2, oy1 + 1 - (cy1 - 3), cq.Vector(_sma_x, cy1 - 3, SMA_Z), cq.Vector(0, 1, 0)))
_fh = SMA_FLANGE / 2 + SMA_FLANGE_CLR
_fx = -(SMA_PROUD + SMA_FLANGE_GAP)
sma_pocket = radio_box(_fx, 0.2, SMA_Y - _fh, SMA_Y + _fh, SMA_Z - _fh, SMA_Z + _fh)

openings = sma_cut.union(sma_pocket)
for name, (nx, zc) in PI_PORTS.items():
    w, h = PORT_OPEN[name]
    gx, _ = pi_xy(nx, 0)
    z = PI_Z0 + PI_T + zc
    openings = openings.union(
        cq.Workplane("XZ").workplane(offset=-(cy1 - 3)).center(gx, z)
        .rect(w, h).extrude(-(WALL + LIP_W + 6)).edges("|Y").fillet(min(w, h) / 2 - 0.01))
_, sd_y = pi_xy(0, PI_SD_Y)
openings = openings.union(box(cx1 - 3, ox1 + 1, sd_y - 8, sd_y + 8, PI_Z0 - 3.0, PI_Z0 + 1.0))

BIAST_HOLE_X = BW + 10.0               # global X of the cable entry, over the gap
openings = openings.union(cq.Workplane("XY").add(cq.Solid.makeCylinder(
    (BIAST_CABLE_D + BIAST_HOLE_CLR) / 2, oy1 + 1 - (cy1 - 3),
    cq.Vector(BIAST_HOLE_X, cy1 - 3, SPLIT), cq.Vector(0, 1, 0))))

# ---------------- vents over and under the Pi, centred on its SoC -------------
VENT_W, VENT_PITCH, VENT_N, VENT_L = 2.0, 5.0, 10, 24.0
_soc_x, _soc_y = pi_xy(*PI_SOC)
vx = [_soc_x + (i - (VENT_N - 1) / 2) * VENT_PITCH for i in range(VENT_N)]
VENT_Y0, VENT_Y1 = _soc_y - VENT_L / 2, _soc_y + VENT_L / 2
def vents(z0, z1):
    v = None
    for x in vx:
        s = rbox(x - VENT_W / 2, VENT_Y0, VENT_W, VENT_Y1 - VENT_Y0, z0, z1, VENT_W / 2 - 0.01)
        v = s if v is None else v.union(s)
    return v

# ---------------- adhesive pads under the radio board -----------------------------
# The radio board has no mounting holes: besides the corner clamp, it sticks to
# four platforms with double-sided foam pads. Platform tops sit PAD_T - PAD_SQUEEZE
# below the board, so each pad is squeezed a little while the board still rests
# on its posts. Spots (radio frame) avoid the SMA and the (unfitted) encoder's leads.
PAD_T = 1.0          # foam tape thickness
PAD_SQUEEZE = 0.2
PAD = 10.0           # square pad / platform size
PAD_PTS = [(15, 15), (55, 15), (15, 55), (45, 60)]
PAD_TOP = -(PAD_T - PAD_SQUEEZE)

# ---------------- base ---------------------------------------------------------
base = rbox(ox0, oy0, ox1 - ox0, oy1 - oy0, z_bot, SPLIT, R_OUT)
base = base.cut(rbox(cx0, cy0, cx1 - cx0, cy1 - cy0, FLOOR_TOP, SPLIT + 1, 0.3))
base = base.union(lip_ring(0.0))
# radio corner posts (board underside Z = 0) and mid-span posts, radio frame
POST = 4.0
for (px, py) in [(0, 0), (BW - POST, 0), (0, BL - POST), (BW - POST, BL - POST),
                 (BW / 2 - 2, 0), (BW / 2 - 2, BL - 3)]:
    base = base.union(radio_box(px, px + POST, py, py + min(POST, BL - py), FLOOR_TOP - 0.1, 0.0))
for (px, py) in PAD_PTS:
    base = base.union(radio_box(px - PAD / 2, px + PAD / 2, py - PAD / 2, py + PAD / 2,
                                FLOOR_TOP - 0.1, PAD_TOP))
# Pi standoffs and the frame screw columns
base = base.union(cyl(pi_screws, BOSS_R, FLOOR_TOP - 0.1, PI_Z0))
base = base.union(cyl(frame_screws, BOSS_R, FLOOR_TOP - 0.1, SPLIT))
base = base.cut(openings).cut(vents(z_bot - 1, FLOOR_TOP + 1))
screws = pi_screws + frame_screws
base = base.cut(cyl(screws, SCREW_CLR / 2, z_bot - 1, SPLIT + 1))
base = base.cut(cyl(screws, CB_D / 2, z_bot - 1, z_bot + CB_DEPTH))
# zip-tie anchor for the bias-T cable: a bar with a slot under it, across the cable
TIE_Y = cy1 - 8.0
base = base.union(box(BIAST_HOLE_X - 5, BIAST_HOLE_X + 5, TIE_Y - 3.5, TIE_Y + 3.5,
                      FLOOR_TOP - 0.1, FLOOR_TOP + 4.5))
base = base.cut(box(BIAST_HOLE_X - 6, BIAST_HOLE_X + 6, TIE_Y - 2.0, TIE_Y + 2.0,
                    FLOOR_TOP + 0.8, FLOOR_TOP + 2.8))
FEET = [(25, cy0 + 8), (25, cy1 - 8), (PI_X0 + 60, cy0 + 8), (PI_X0 + 55, cy1 - 8)]
base = base.cut(cyl(FEET, 4.3, z_bot - 1, z_bot + 0.6))

# hardware label on the underside, reading correctly when the box is turned over
SCREW_LABEL = f"{len(pi_screws) + len(frame_screws)}x M2.5 x 12 SCREWS"
def engrave_bottom(body, text, x, y, size):
    pl = cq.Plane(origin=(x, y, z_bot), xDir=(1, 0, 0), normal=(0, 0, -1))
    return body.cut(cq.Workplane(pl).text(text, size, -0.6, kind="bold", halign="center", valign="center"))
base = engrave_bottom(base, SCREW_LABEL, BW / 2, 38, 4.0)
base = engrave_bottom(base, "4x 8 MM FEET  /  1 MM FOAM PADS", BW / 2, 30, 2.6)

# ---------------- lid ----------------------------------------------------------
lid = rbox(ox0, oy0, ox1 - ox0, oy1 - oy0, SPLIT, z_top, R_OUT)
lid = lid.cut(rbox(cx0, cy0, cx1 - cx0, cy1 - cy0, SPLIT - 1, CEIL, 0.3))
lid = lid.cut(rbox(cx0 - LIP_W - LIP_CLR, cy0 - LIP_W - LIP_CLR,
                   cx1 - cx0 + 2 * (LIP_W + LIP_CLR), cy1 - cy0 + 2 * (LIP_W + LIP_CLR),
                   SPLIT - 1, SPLIT + LIP_H + LIP_CLR, 0.8))
# radio clamp pins, radio frame
PIN = 3.0
for (px, py) in [(0.4, 0.4), (BW - PIN - 0.4, 0.4), (0.4, BL - PIN - 0.4),
                 (BW - PIN - 0.4, BL - PIN - 0.4)]:
    lid = lid.union(radio_box(px, px + PIN, py, py + PIN, SPLIT + 0.05, CEIL + 0.1))
# screw bosses: press the Pi down at its holes; frame columns meet the base posts
lid = lid.union(cyl(pi_screws, BOSS_R, PI_Z0 + PI_T + 0.05, CEIL + 0.1))
lid = lid.union(cyl(frame_screws, BOSS_R, SPLIT, CEIL + 0.1))
lid = lid.cut(openings).cut(vents(CEIL - 1, z_top + 1))
lid = lid.cut(cyl(pi_screws, SCREW_PILOT / 2, PI_Z0, CEIL - 1.0))
lid = lid.cut(cyl(frame_screws, SCREW_PILOT / 2, SPLIT - 1, CEIL - 1.0))

def engrave_top(body, text, x, y, size):
    t = (cq.Workplane("XY").workplane(offset=z_top - 0.6).center(x, y)
         .text(text, size, 1.0, kind="bold", halign="center", valign="center"))
    return body.cut(t)

lid = engrave_top(lid, "TAYLOE SDR", BW / 2, 42, 6.0)
lid = engrave_top(lid, "MAHJOUB'S STUDIO", BW / 2, 32, 3.2)
# "ANT" on the back wall beside the SMA, reading left to right from behind
_ap = cq.Plane(origin=(_sma_x + 12, oy1, (SPLIT + CEIL) / 2), xDir=(-1, 0, 0), normal=(0, 1, 0))
lid = lid.cut(cq.Workplane(_ap).text("ANT", 3.2, -0.6, kind="bold", halign="center", valign="center"))

# ---------------- real Pi model ---------------------------------------------------
PI_STEP = os.path.join(os.path.dirname(__file__), "..", "rpi-step", "pi3bplus.step")

def pi_real():
    """The STEP model placed with pi_xy(); it is Y-up with the board centred on X."""
    m = cq.importers.importStep(PI_STEP)
    # model -> native: x = X + 42.5, y = 31.5 - Z, z = Y; with the 180 degree turn
    # that is global (-X, Z, Y) + offset: +90 about X, then 180 about Z
    off = cq.Vector(PI_X0 + 42.5, PI_Y0 + PI_L - 31.5, PI_Z0)
    return cq.Workplane("XY").add(cq.Compound.makeCompound(
        [s.rotate(cq.Vector(), cq.Vector(1, 0, 0), 90)
          .rotate(cq.Vector(), cq.Vector(0, 0, 1), 180).translate(off)
         for s in m.solids().vals()]))

def place_radio(shape):
    """Radio-frame shape -> global, matching radio_xy()."""
    return shape.rotate(cq.Vector(), cq.Vector(0, 0, 1), -90).translate(cq.Vector(0, BW, 0))

# ---------------- checks -------------------------------------------------------
radio_raw = cq.importers.importStep(sys.argv[2]).solids().vals()
radio_all = [place_radio(s) for s in radio_raw]
radio_parts = [place_radio(s) for s in radio_raw
               if not (s.BoundingBox().xmin > 53 and s.BoundingBox().ymin > 43
                       and s.BoundingBox().zmax > 10)]          # encoder not fitted
radio = cq.Compound.makeCompound(radio_all)
pi = pi_real()
_under = None
for (a, b, c, d, h) in PI_UNDER.values():
    (gx0, gy0), (gx1, gy1) = pi_xy(a, c), pi_xy(b, d)
    u = box(gx0, gx1, gy0, gy1, PI_Z0 - h, PI_Z0)
    _under = u if _under is None else _under.union(u)
pi = pi.add(_under.vals())
pi_bb = cq.Compound.makeCompound(pi.vals()).BoundingBox()
print(f"Pi model placed: x {pi_bb.xmin:.2f}..{pi_bb.xmax:.2f} y {pi_bb.ymin:.2f}..{pi_bb.ymax:.2f} "
      f"z {pi_bb.zmin:.2f}..{pi_bb.zmax:.2f}")
# room the cable needs: both plugs plus slack, straight across the gap
_c_x, _c_y = radio_xy(RADIO_USBC_X, RADIO_USBC_MOUTH)
_a_x, _a_y = pi_xy(PI_W + PI_USB_PROUD, PI_USB_Y)
_a_z = PI_Z0 + PI_USB_LOW_Z
_ylo, _yhi = min(_c_y, _a_y) - 8, max(_c_y, _a_y) + 8
plug_room = {
    # overmold ~12 x 7 mm, from the board edge (the metal shell is inside the receptacle)
    "usb_c_plug": box(BW, _c_x + USB_C_PLUG, _c_y - 6, _c_y + 6, RADIO_USBC_Z - 3.5, RADIO_USBC_Z + 3.5),
    "usb_a_plug": box(_a_x - USB_A_PLUG, _a_x, _a_y - 8, _a_y + 8, _a_z - 5, _a_z + 5),
    "cable_run": box(_c_x + USB_C_PLUG, _a_x - USB_A_PLUG, _ylo, _yhi, 0.0, _a_z + 5),
}
# the bias-T cable, a separate cable that never reaches the radio: wall entry ->
# over the tie anchor -> along the gap -> USB-A plug in the Pi's back stack
_b_x, _b_y = pi_xy(PI_W + PI_USB_PROUD, BIAST_USB_Y)
_br = BIAST_CABLE_D / 2 + 0.5
_tie_top = FLOOR_TOP + 4.6                 # cable rides on top of the tie bar
biast_room = {
    "biast_entry": box(BIAST_HOLE_X - _br, BIAST_HOLE_X + _br, TIE_Y + 3.6, cy1, SPLIT - _br, SPLIT + _br),
    "biast_run": box(BIAST_HOLE_X - _br, BIAST_HOLE_X + _br, _b_y - _br, TIE_Y + 3.6, _tie_top, _a_z + _br)
                 .union(box(BIAST_HOLE_X - _br, _b_x - USB_A_PLUG, _b_y - _br, _b_y + _br, _tie_top, _a_z + _br)),
    "biast_plug": box(_b_x - USB_A_PLUG, _b_x, _b_y - 8, _b_y + 8, _a_z - 5, _a_z + 5),
}

def clash(a, b):
    """Overlap volume between two Workplanes (each may hold several shapes)."""
    sa, sb = cq.Compound.makeCompound(a.vals()), cq.Compound.makeCompound(b.vals())
    return sa.intersect(sb).Volume()

L, D = ox1 - ox0, oy1 - oy0
print(f"outer {L:.1f} x {D:.1f} x {z_top - z_bot:.1f} mm "
      f"(cavity {cx1 - cx0:.1f} x {cy1 - cy0:.1f}, ceiling Z {CEIL:.1f}); "
      f"fits 220 mm bed straight: {L <= 220 and D <= 220}, diagonally: {(L + D) / 2 ** 0.5 <= 220}")
print(f"cable: USB-C mouth ({_c_x:.1f}, {_c_y:.1f}, Z {RADIO_USBC_Z:.2f}) -> Pi USB-A face "
      f"({_a_x:.1f}, {_a_y:.1f}, Z {_a_z:.2f}); gap {CABLE_GAP:.1f} mm")
print(f"base valid {base.val().isValid()}, lid valid {lid.val().isValid()}, "
      f"base/lid overlap {clash(base, lid):.3f} mm3")
for name, part in (("base", base), ("lid", lid)):
    hits = [s for s in radio_parts if part.val().intersect(s).Volume() > 1e-3]
    print(f"{name}: radio-board overlaps {len(hits)}, Pi overlap {clash(part, pi):.2f} mm3, "
          + ", ".join(f"{k} {clash(part, v):.2f} mm3" for k, v in {**plug_room, **biast_room}.items()))
print("Pi vs radio board:", round(sum(pi.val().intersect(s).Volume() for s in radio_parts), 3))
_pcb = max(radio_parts, key=lambda s: s.BoundingBox().xlen * s.BoundingBox().ylen)
_parts = [s for s in radio_parts if s is not _pcb]
_pc = cq.Compound.makeCompound(_parts)
for k, v in {**plug_room, **biast_room}.items():
    print(f"{k}: vs radio parts {v.val().intersect(_pc).Volume():.2f} mm3, "
          f"vs Pi {clash(v, pi):.2f} mm3")
pads = [radio_box(px - PAD / 2, px + PAD / 2, py - PAD / 2, py + PAD / 2, PAD_TOP, 0.0).val()
        for (px, py) in PAD_PTS]
print(f"adhesive pads: {len(pads)} x {PAD:.0f} mm, platform top Z {PAD_TOP:.2f}; pad space vs radio parts "
      f"{sum(p.intersect(s).Volume() for p in pads for s in _parts):.3f} mm3")

# ---------------- export -------------------------------------------------------
def on_bed(part, bottom, flip=False):
    if flip:
        part = part.rotate((0, 0, 0), (1, 0, 0), 180)
        bottom = -bottom
    return part.translate((0, 0, -bottom))

for name, part in (("pi_base", base), ("pi_lid", lid)):
    cq.exporters.export(part, f"{OUT}/{name}.step")
for name, part in (("pi_base", on_bed(base, z_bot)), ("pi_lid", on_bed(lid, z_top, flip=True))):
    cq.exporters.export(part, f"{OUT}/print/{name}.stl", tolerance=0.02, angularTolerance=0.1)
    cq.exporters.export(part, f"{OUT}/print/{name}.3mf", tolerance=0.02, angularTolerance=0.1)
    cq.exporters.export(part, f"{OUT}/print/{name}.step")
cq.exporters.export(cq.Compound.makeCompound(pi.vals()), f"{OUT}/pi3bplus_placed.step")
cq.exporters.export(radio, f"{OUT}/radio_placed.step")
cq.exporters.export(cq.Compound.makeCompound([v.val() for v in plug_room.values()]),
                    f"{OUT}/cable_keepout.step")          # radio USB-C -> Pi
cq.exporters.export(cq.Compound.makeCompound([v.val() for v in biast_room.values()]),
                    f"{OUT}/biast_keepout.step")          # bias-T power -> Pi

asm = cq.Assembly(name="tayloe_sdr_pi_enclosure")
asm.add(radio, name="radio_pcb")
asm.add(cq.Compound.makeCompound(pi.vals()), name="pi3bplus", color=cq.Color(0.15, 0.45, 0.2))
asm.add(base, name="base", color=cq.Color(0.20, 0.22, 0.25))
asm.add(lid, name="lid", color=cq.Color(0.20, 0.22, 0.25, 0.35))
asm.save(f"{OUT}/pi_enclosure_assembly.step")

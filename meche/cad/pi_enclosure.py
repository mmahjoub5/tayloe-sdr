"""Combined enclosure: Tayloe SDR board + Raspberry Pi 3 B+ side by side.

Usage: python cad/pi_enclosure.py <out dir> <radio-project.step>

Frame: the radio board's (X 0..70, Y 0..70, Z 0..1.42), as in enclosure.py.
The Pi sits to the right, turned 180 degrees so its USB/Ethernet edge faces
the radio: a short right-angle USB-C to right-angle USB-A cable joins the two
inside the box. The Pi's power/HDMI/audio edge faces the back wall and its SD
slot the right wall; the radio's SMA leaves through the left wall.

Parting line is the radio board's top (Z = 1.42), as before. Seven M2.5 x 12
screws go in from below: four through the Pi's own mounting holes (clamping
the Pi between its standoffs and the lid) and three into posts at the radio
end. Fit checks use the Pi 3 B+ model in rpi-step/pi3bplus.step (GrabCAD,
matches the official drawing to within ~1 mm). That model has nothing under
the board, so the SD card and GPIO pin tails come from the drawing.
"""
import os
import sys
import cadquery as cq

OUT = sys.argv[1]
os.makedirs(f"{OUT}/print", exist_ok=True)

# ---------------- radio board (measured from the STEP, as in enclosure.py) -----
BW, BL, BT = 70.0, 70.0, 1.42
SPLIT = BT                             # parting plane = radio board top
SMA_Y, SMA_Z = 14.17, 2.00
SMA_THREAD, SMA_FLANGE = 6.35, 6.35
SMA_CLR, SMA_FLANGE_CLR = 0.45, 0.5
SMA_PROUD = 2.0                        # hand-soldered flange may sit this far out
SMA_FLANGE_GAP = 0.3
SMA_D = SMA_THREAD + 2 * SMA_CLR
RADIO_USBC_X = 34.72                   # USB-C on the back edge; cable stays inside

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

# ---------------- layout -------------------------------------------------------
# internal USB cable: straight plugs, two 90 degree bends (radio USB-C points back
# into the channel, the cable runs right along it, then turns into the Pi's USB-A)
USB_C_PLUG = 25.0    # straight USB-C plug, overmold + strain relief, beyond the port
USB_A_PLUG = 28.0    # straight USB-A plug, likewise
CABLE_BEND = 12.0    # room for each 90 degree bend
PI_USB_PROUD = 2.5   # Pi USB/Ethernet stick out past its board edge (STEP model)
CABLE_GAP = PI_USB_PROUD + USB_A_PLUG + CABLE_BEND    # radio right edge -> Pi board edge
CHANNEL = USB_C_PLUG + CABLE_BEND                     # behind the radio
FRONT = 7.0          # in front of the radio: room for the front screw posts
PI_STANDOFF = 4.5    # clears the GPIO pins and SD socket under the Pi
GAP = 0.3            # board-to-wall clearance

WALL = 2.4
FLOOR = 2.0
FLOOR_TOP = -3.0
TOP = 2.0
LIP_W, LIP_H, LIP_CLR = 1.0, 1.5, 0.2
R_OUT = 3.0

PI_X0 = BW + CABLE_GAP                 # Pi footprint in the global frame
PI_Y0 = BL + CHANNEL - PI_L            # Pi's port edge flush with the radio channel's back
PI_Z0 = FLOOR_TOP + PI_STANDOFF        # Pi board underside
CEIL = PI_Z0 + PI_T + max(v[4] for v in PI_TOP.values()) + 1.0   # over the USB stack

cx0, cy0 = -GAP, -(GAP + FRONT)
cx1, cy1 = PI_X0 + PI_W + GAP, PI_Y0 + PI_L + GAP
ox0, oy0, ox1, oy1 = cx0 - WALL, cy0 - WALL, cx1 + WALL, cy1 + WALL
z_bot, z_top = FLOOR_TOP - FLOOR, CEIL + TOP

def pi_xy(x, y):
    """Native Pi coordinates -> global (the Pi is turned 180 degrees)."""
    return PI_X0 + (PI_W - x), PI_Y0 + (PI_L - y)

# ---------------- screws (M2.5 x 12 from below) -------------------------------
BOSS_R = 3.0
SCREW_CLR, SCREW_PILOT = 2.9, 2.2
CB_D, CB_DEPTH = 5.5, 3.0
pi_screws = [pi_xy(x, y) for (x, y) in PI_HOLES]
frame_screws = [(3.5, cy0 + 3.5), (3.5, cy1 - 3.5), (BW + CABLE_GAP / 2, cy0 + 3.5)]

# ---------------- helpers ------------------------------------------------------
def rbox(x0, y0, w, l, z0, z1, r=0.0):
    s = (cq.Workplane("XY").workplane(offset=z0).center(x0 + w / 2, y0 + l / 2)
         .rect(w, l).extrude(z1 - z0))
    return s.edges("|Z").fillet(r) if r > 0 else s

def box(x0, x1, y0, y1, z0, z1):
    return rbox(min(x0, x1), min(y0, y1), abs(x1 - x0), abs(y1 - y0), z0, z1)

def cyl(pts, r, z0, z1):
    return cq.Workplane("XY").workplane(offset=z0).pushPoints(pts).circle(r).extrude(z1 - z0)

def lip_ring(clr):
    outer = rbox(cx0 - LIP_W - clr, cy0 - LIP_W - clr, cx1 - cx0 + 2 * (LIP_W + clr),
                 cy1 - cy0 + 2 * (LIP_W + clr), SPLIT, SPLIT + LIP_H + clr, 0.8)
    inner = rbox(cx0 - clr, cy0 - clr, cx1 - cx0 + 2 * clr, cy1 - cy0 + 2 * clr,
                 SPLIT - 1, SPLIT + LIP_H + 2, 0.3)
    return outer.cut(inner)

# ---------------- approximate Pi model (for fit checks and the assembly) -------
def pi_model():
    hx = [pi_xy(x, y) for (x, y) in PI_HOLES]
    x0, y0 = pi_xy(PI_W, PI_L)
    m = rbox(x0, y0, PI_W, PI_L, PI_Z0, PI_Z0 + PI_T, 3.0).cut(cyl(hx, 1.375, PI_Z0 - 1, PI_Z0 + 3))
    for (a, b, c, d, h) in PI_TOP.values():
        (gx0, gy0), (gx1, gy1) = pi_xy(a, c), pi_xy(b, d)
        m = m.union(box(gx0, gx1, gy0, gy1, PI_Z0 + PI_T, PI_Z0 + PI_T + h))
    for (a, b, c, d, h) in PI_UNDER.values():
        (gx0, gy0), (gx1, gy1) = pi_xy(a, c), pi_xy(b, d)
        m = m.union(box(gx0, gx1, gy0, gy1, PI_Z0 - h, PI_Z0))
    return m

# ---------------- openings -----------------------------------------------------
sma_cut = (cq.Workplane("YZ").workplane(offset=ox0 - 1).center(SMA_Y, SMA_Z)
           .circle(SMA_D / 2).extrude(WALL + LIP_W + 3))
_fh = SMA_FLANGE / 2 + SMA_FLANGE_CLR
_fx = -(SMA_PROUD + SMA_FLANGE_GAP)
sma_pocket = rbox(_fx, SMA_Y - _fh, 0.2 - _fx, 2 * _fh, SMA_Z - _fh, SMA_Z + _fh)

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

# ---------------- vents over and under the Pi -----------------------------------
VENT_W, VENT_PITCH = 2.0, 5.0
vx = [PI_X0 + 25 + i * VENT_PITCH for i in range(10)]
VENT_Y0, VENT_Y1 = PI_Y0 + 15, PI_Y0 + 39
def vents(z0, z1):
    v = None
    for x in vx:
        s = rbox(x - VENT_W / 2, VENT_Y0, VENT_W, VENT_Y1 - VENT_Y0, z0, z1, VENT_W / 2 - 0.01)
        v = s if v is None else v.union(s)
    return v

# ---------------- base ---------------------------------------------------------
base = rbox(ox0, oy0, ox1 - ox0, oy1 - oy0, z_bot, SPLIT, R_OUT)
base = base.cut(rbox(cx0, cy0, cx1 - cx0, cy1 - cy0, FLOOR_TOP, SPLIT + 1, 0.3))
base = base.union(lip_ring(0.0))
# radio corner posts (board underside Z = 0) and mid-span posts
POST = 4.0
for (px, py) in [(0, 0), (BW - POST, 0), (0, BL - POST), (BW - POST, BL - POST),
                 (BW / 2 - 2, 0), (BW / 2 - 2, BL - 3)]:
    base = base.union(rbox(px, py, POST, min(POST, BL - py), FLOOR_TOP - 0.1, 0.0))
# Pi standoffs and the frame screw columns
base = base.union(cyl(pi_screws, BOSS_R, FLOOR_TOP - 0.1, PI_Z0))
base = base.union(cyl(frame_screws, BOSS_R, FLOOR_TOP - 0.1, SPLIT))
base = base.cut(openings).cut(vents(z_bot - 1, FLOOR_TOP + 1))
screws = pi_screws + frame_screws
base = base.cut(cyl(screws, SCREW_CLR / 2, z_bot - 1, SPLIT + 1))
base = base.cut(cyl(screws, CB_D / 2, z_bot - 1, z_bot + CB_DEPTH))
FEET = [(25, cy0 + 8), (25, cy1 - 8), (PI_X0 + 60, cy0 + 8), (PI_X0 + 55, cy1 - 8)]
base = base.cut(cyl(FEET, 4.3, z_bot - 1, z_bot + 0.6))

# ---------------- lid ----------------------------------------------------------
lid = rbox(ox0, oy0, ox1 - ox0, oy1 - oy0, SPLIT, z_top, R_OUT)
lid = lid.cut(rbox(cx0, cy0, cx1 - cx0, cy1 - cy0, SPLIT - 1, CEIL, 0.3))
lid = lid.cut(rbox(cx0 - LIP_W - LIP_CLR, cy0 - LIP_W - LIP_CLR,
                   cx1 - cx0 + 2 * (LIP_W + LIP_CLR), cy1 - cy0 + 2 * (LIP_W + LIP_CLR),
                   SPLIT - 1, SPLIT + LIP_H + LIP_CLR, 0.8))
# radio clamp pins
PIN = 3.0
for (px, py) in [(0.4, 0.4), (BW - PIN - 0.4, 0.4), (0.4, BL - PIN - 0.4),
                 (BW - PIN - 0.4, BL - PIN - 0.4)]:
    lid = lid.union(rbox(px, py, PIN, PIN, SPLIT + 0.05, CEIL + 0.1))
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
_ap = cq.Plane(origin=(ox0, SMA_Y + 12, (SPLIT + CEIL) / 2), xDir=(0, -1, 0), normal=(-1, 0, 0))
lid = lid.cut(cq.Workplane(_ap).text("ANT", 3.2, -0.6, kind="bold", halign="center", valign="center"))

# ---------------- real Pi model ---------------------------------------------------
PI_STEP = os.path.join(os.path.dirname(__file__), "..", "rpi-step", "pi3bplus.step")

def pi_real():
    """The STEP model placed like pi_model(); it is Y-up with the board centred on X."""
    m = cq.importers.importStep(PI_STEP)
    # model -> native: x = X + 42.5, y = 31.5 - Z, z = Y; with the 180 degree turn
    # that is global (-X, Z, Y) + offset: +90 about X, then 180 about Z
    off = cq.Vector(PI_X0 + 42.5, PI_Y0 + PI_L - 31.5, PI_Z0)
    return cq.Workplane("XY").add(cq.Compound.makeCompound(
        [s.rotate(cq.Vector(), cq.Vector(1, 0, 0), 90)
          .rotate(cq.Vector(), cq.Vector(0, 0, 1), 180).translate(off)
         for s in m.solids().vals()]))

# ---------------- checks -------------------------------------------------------
radio = cq.importers.importStep(sys.argv[2])
radio_parts = [s for s in radio.solids().vals()
               if not (s.BoundingBox().xmin > 53 and s.BoundingBox().ymin > 43
                       and s.BoundingBox().zmax > 10)]          # encoder not fitted
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
# room the cable plugs need (right-angle plugs, generous)
_ua_x, _ua_y = pi_xy(85.0, 29.0)     # nearer USB stack, at the Pi's board edge
plug_room = {
    "usb_c_plug": box(RADIO_USBC_X - 6, RADIO_USBC_X + 6, BL, BL + USB_C_PLUG, 0.0, 9.0),
    "usb_a_plug": box(_ua_x - PI_USB_PROUD - USB_A_PLUG, _ua_x - PI_USB_PROUD, _ua_y - 8, _ua_y + 8,
                      PI_Z0 + PI_T, PI_Z0 + PI_T + 9.5),
    # the cable run: along the channel, then down the gap to the plug
    "cable_run": box(RADIO_USBC_X - 3, PI_X0 - PI_USB_PROUD - USB_A_PLUG + 3,
                     BL + USB_C_PLUG, BL + CHANNEL, 0.0, 9.0).union(
                 box(BW + 1, PI_X0 - PI_USB_PROUD - USB_A_PLUG, _ua_y - 3, BL + CHANNEL, 0.0, 9.0)),
}

def clash(a, b):
    """Overlap volume between two Workplanes (each may hold several shapes)."""
    sa, sb = cq.Compound.makeCompound(a.vals()), cq.Compound.makeCompound(b.vals())
    return sa.intersect(sb).Volume()

print(f"outer {ox1 - ox0:.1f} x {oy1 - oy0:.1f} x {z_top - z_bot:.1f} mm "
      f"(cavity {cx1 - cx0:.1f} x {cy1 - cy0:.1f}, ceiling Z {CEIL:.1f})")
print(f"base valid {base.val().isValid()}, lid valid {lid.val().isValid()}, "
      f"base/lid overlap {clash(base, lid):.3f} mm3")
for name, part in (("base", base), ("lid", lid)):
    hits = [s for s in radio_parts if part.val().intersect(s).Volume() > 1e-3]
    print(f"{name}: radio-board overlaps {len(hits)}, Pi overlap {clash(part, pi):.2f} mm3, "
          + ", ".join(f"{k} {clash(part, v):.2f} mm3" for k, v in plug_room.items()))
print("Pi vs radio board:", round(sum(pi.val().intersect(s).Volume() for s in radio_parts), 3))

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

asm = cq.Assembly(name="tayloe_sdr_pi_enclosure")
asm.add(radio, name="radio_pcb")
asm.add(cq.Compound.makeCompound(pi.vals()), name="pi3bplus", color=cq.Color(0.15, 0.45, 0.2))
asm.add(base, name="base", color=cq.Color(0.20, 0.22, 0.25))
asm.add(lid, name="lid", color=cq.Color(0.20, 0.22, 0.25, 0.35))
asm.save(f"{OUT}/pi_enclosure_assembly.step")

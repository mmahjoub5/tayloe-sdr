"""Render a .grc to PNG with GRC's own canvas code (no window) and report layout problems.

    $GR/bin/python grc_render.py flowgraph.grc out.png

Prints the canvas size, every block's box, overlapping blocks or comments, and GRC's validation errors.
The picture matches GRC's default view (variables shown, block IDs hidden, comments shown).
"""

import sys

import cairo
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Gtk  # noqa: E402

# GRC's canvas asks for the running app's windows and builds a context menu; neither exists here.
Gtk.Application.get_default = staticmethod(lambda: type("App", (), {"get_windows": lambda self: []})())

from gnuradio import gr  # noqa: E402
from gnuradio.grc.gui.Platform import Platform  # noqa: E402  (before Actions: GRC's imports are circular)
from gnuradio.grc.gui import Actions  # noqa: E402
from gnuradio.grc.gui.canvas import flowgraph as canvas_flowgraph  # noqa: E402

canvas_flowgraph._ContextMenu = lambda main_window: None

# GRC's default view; without the app every toggle reads True.
VIEW = {
    "TOGGLE_HIDE_DISABLED_BLOCKS": False, "TOGGLE_HIDE_VARIABLES": False,
    "TOGGLE_SHOW_PARAMETER_EXPRESSION": False, "TOGGLE_SHOW_PARAMETER_EVALUATION": True,
    "TOGGLE_SHOW_BLOCK_IDS": False, "TOGGLE_SHOW_FIELD_COLORS": False,
    "TOGGLE_AUTO_HIDE_PORT_LABELS": False, "TOGGLE_SHOW_BLOCK_COMMENTS": True,
}
MARGIN = 60
OVERLAP_PX = 8                              # closer than this (ports included) and boxes collide
TIGHT_PX = 40                               # blocks closer than this leave no room for a visible wire


def load(path: str):
    """
    Load a flowgraph into GRC's canvas classes and lay out its labels.

    Args:
        path (str): the .grc file

    Returns:
        FlowGraph: GRC's canvas flowgraph, validated, with block sizes computed
    """
    for name, state in VIEW.items():
        getattr(Actions, name).set_active(state)
    platform = Platform(version=gr.version(),
                        version_parts=(gr.major_version(), gr.api_version(), gr.minor_version()),
                        prefs=gr.prefs(), install_prefix=gr.prefix())
    platform.build_library()
    fg = platform.make_flow_graph(path)
    fg.import_data(platform.parse_flow_graph(path))
    fg.rewrite()
    fg.validate()
    fg.update_elements_to_draw()
    fg.create_labels(cairo.Context(cairo.ImageSurface(cairo.FORMAT_ARGB32, 1, 1)))
    fg.create_shapes()
    return fg


def boxes(fg) -> list[tuple[str, tuple[float, float, float, float]]]:
    """
    Collect every block's box (ports included) and every comment's box.

    Args:
        fg (FlowGraph): a loaded flowgraph

    Returns:
        list[tuple[str, tuple]]: (label, (x0, y0, x1, y1)); comments are labelled "<name> comment"
    """
    out = []
    for b in fg.blocks:
        out.append((b.name, b.get_extents()))
        c = b.get_extents_comment()
        if c[2] > c[0]:
            out.append((f"{b.name} comment", c))
    return out


def overlaps(items: list, gap: float) -> list[tuple[str, str]]:
    """
    Find pairs of boxes closer than a gap.

    Args:
        items (list): (label, (x0, y0, x1, y1)) from boxes()
        gap (float): clearance in px

    Returns:
        list[tuple[str, str]]: the labels of each clashing pair
    """
    clash = []
    for i, (n1, (a0, b0, a1, b1)) in enumerate(items):
        for n2, (c0, d0, c1, d1) in items[i + 1:]:
            if n2 == f"{n1} comment":
                continue                    # a comment always sits just under its own block
            if a0 < c1 + gap and c0 < a1 + gap and b0 < d1 + gap and d0 < b1 + gap:
                clash.append((n1, n2))
    return clash


def main():
    """Render the flowgraph and print the report."""
    src, out = sys.argv[1], sys.argv[2]
    fg = load(src)
    items = boxes(fg)
    w = int(max(x1 for _, (_, _, x1, _) in items) + MARGIN)
    h = int(max(y1 for _, (_, _, _, y1) in items) + MARGIN)
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    cr = cairo.Context(surf)
    cr.set_source_rgb(1, 1, 1)
    cr.paint()
    fg.create_labels(cr)
    fg.create_shapes()
    fg.draw(cr)
    surf.write_to_png(out)

    print(f"canvas {w} x {h} px -> {out}")
    clash = overlaps(items, OVERLAP_PX)
    print("overlaps:" if clash else "overlaps: none")
    for a, b in clash:
        print(f"  {a}  <->  {b}")
    blocks_only = [i for i in items if not i[0].endswith(" comment")]
    tight = [p for p in overlaps(blocks_only, TIGHT_PX) if p not in clash]
    print(f"tight (< {TIGHT_PX} px apart):" if tight else "tight: none")
    for a, b in tight:
        print(f"  {a}  <->  {b}")
    errors = [(b.name, e) for b in fg.blocks for e in b.get_error_messages()]
    print("errors:" if errors else "errors: none")
    for name, e in errors:
        print(f"  {name}: {e}")


if __name__ == "__main__":
    sys.exit(main())

"""Pack the board and the generated STEP parts into a FreeCAD document.

Usage (run from meche/, after enclosure.py):
    /Applications/FreeCAD.app/Contents/MacOS/FreeCAD cad/to_fcstd.py
It must run in the FreeCAD GUI (a window opens and closes): freecadcmd
saves no colours, visibility or transparency, so the board ends up hidden
inside an opaque box.
"""
import os
import FreeCAD
import FreeCADGui
import Import

OUT = os.path.join(os.getcwd(), "out")
BOARD = os.path.join(os.getcwd(), "..", "radio-project", "radio-project.step")
STYLE = {  # label: (rgb, transparency %)
    "enclosure_base": ((0.20, 0.22, 0.25), 0),
    "enclosure_lid": ((0.20, 0.22, 0.25), 70),
}

doc = FreeCAD.newDocument("enclosure")
for label, path in [("pcb", BOARD)] + [
        (n, os.path.join(OUT, f"{n}.step")) for n in STYLE]:
    before = set(doc.Objects)
    Import.insert(path, doc.Name)
    new = [o for o in doc.Objects if o not in before]
    top = [o for o in new if not any(o in p.OutList for p in new)][0]
    top.Label = label
    top.ViewObject.Visibility = True
    if label in STYLE:
        rgb, pct = STYLE[label]
        top.ViewObject.ShapeColor = rgb
        top.ViewObject.Transparency = pct
doc.recompute()
view = FreeCADGui.getDocument(doc.Name).ActiveView
view.viewIsometric()
view.fitAll()
doc.saveAs(os.path.join(OUT, "enclosure.FCStd"))
FreeCAD.closeDocument(doc.Name)
FreeCADGui.getMainWindow().close()

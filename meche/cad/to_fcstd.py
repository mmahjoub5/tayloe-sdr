"""Pack the board and the generated STEP parts into a FreeCAD document.

Usage: freecadcmd cad/to_fcstd.py   (run from meche/, after enclosure.py)
"""
import os
import FreeCAD
import Import

OUT = os.path.join(os.getcwd(), "out")
BOARD = os.path.join(os.getcwd(), "..", "radio-project", "radio-project.step")
doc = FreeCAD.newDocument("enclosure")
for label, path in [("pcb", BOARD)] + [
        (n, os.path.join(OUT, f"{n}.step")) for n in ("enclosure_base", "enclosure_lid", "knob")]:
    before = set(doc.Objects)
    Import.insert(path, doc.Name)
    new = [o for o in doc.Objects if o not in before]
    top = [o for o in new if not any(o in p.OutList for p in new)]
    top[0].Label = label
doc.recompute()
doc.saveAs(os.path.join(OUT, "enclosure.FCStd"))
print("saved", [o.Label for o in doc.RootObjects])

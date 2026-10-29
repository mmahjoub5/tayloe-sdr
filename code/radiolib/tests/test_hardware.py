import builtins
import importlib
import sys


def test_hardware_needs_no_third_party_imports(monkeypatch):
    real_import = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name.split(".")[0] in ("numpy", "scipy", "serial"):
            raise AssertionError(f"hardware.py imported {name}")
        return real_import(name, *args, **kwargs)

    monkeypatch.delitem(sys.modules, "radiolib.hardware", raising=False)
    monkeypatch.setattr(builtins, "__import__", guarded)
    importlib.import_module("radiolib.hardware")


def test_dsp_imports_without_pyserial(monkeypatch):
    for mod in [m for m in sys.modules if m == "radiolib" or m.startswith("radiolib.")]:
        monkeypatch.delitem(sys.modules, mod)
    monkeypatch.setitem(sys.modules, "serial", None)   # import serial -> ImportError
    radiolib = importlib.import_module("radiolib")
    assert callable(radiolib.demod)

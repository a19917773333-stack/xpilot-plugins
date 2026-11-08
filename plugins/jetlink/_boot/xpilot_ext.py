"""Make store plugins importable in Jetlink's provisioning subprocess.

The manager loads an installed plugin with importlib and does not put
xpilot_plugins on PYTHONPATH. This module lives on the child's PYTHONPATH and
turns itself into the xpilot_ext package, so xpilot_ext.jetlink.seam resolves
to the installed plugin without changing the host.
"""
from pathlib import Path

__path__ = [str(Path(__file__).resolve().parents[2])]

"""A store PythonProcess does not inherit the old bridge's systemd PYTHONPATH.
The existing private OpenCV install must be reused without installing packages or
altering the host process. Import remains lazy until actual camera demand.
"""
import subprocess
import sys


def test_legacy_opencv_install_is_reused_in_the_child(tmp_path):
  package = tmp_path / 'cv2'
  package.mkdir()
  (package / '__init__.py').write_text("__version__ = 'existing-private-runtime'\n")
  script = '''
import sys
from phone_vision.dependencies import load_opencv
# Simulate a standard device venv without globally installed OpenCV.
class Block:
  def find_spec(self, name, path=None, target=None):
    if name == 'cv2' and not any(p == sys.argv[1] for p in sys.path):
      raise ModuleNotFoundError("No cv2", name='cv2')
    if name == 'cv2':
      from importlib.machinery import PathFinder
      return PathFinder.find_spec(name, [sys.argv[1]])
sys.meta_path.insert(0, Block())
print(load_opencv((sys.argv[1],)).__version__)
'''
  result = subprocess.run([sys.executable, '-c', script, str(tmp_path)], capture_output=True, text=True)
  assert result.returncode == 0, result.stderr
  assert result.stdout.strip() == 'existing-private-runtime'

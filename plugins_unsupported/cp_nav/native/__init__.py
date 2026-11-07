"""Carrot native navigation calculations; publishing is captured internally.
OS time/network administration and legacy navigation ingress are not exposed.
"""
from .part0 import Part0
from .part1 import Part1
from .part2 import Part2

class NativeCarrot(Part0,Part1,Part2):
  def __init__(self, params, memory):
    self.params, self.params_memory = params, memory
    self._initialize()

  def update_nav_instruction(self, sm):
    raise RuntimeError('Legacy navigation fallback is unavailable; CP v2 source must be qualified')

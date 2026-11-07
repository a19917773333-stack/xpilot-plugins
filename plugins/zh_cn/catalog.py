"""Exact UI phrases and bounded known display compositions; never rewrite protocol/parameter values."""
import json
from pathlib import Path
import re

DISTANCE_UNITS = {'m': '米', 'km': '公里'}


class ChineseCatalog:
  language = 'zh-CHS'

  def __init__(self):
    self.font_path = Path(__file__).with_name('NotoSansCJKsc-Regular.otf')
    self.strings = json.loads(Path(__file__).with_name('strings.json').read_text(encoding='utf-8'))
    self.glyphs = ''.join(sorted(set(''.join(self.strings.values()) + ''.join(DISTANCE_UNITS.values()))))

  def translate(self, text):
    if text in self.strings:
      return self.strings[text]
    # Plugin version/author are identities; translate only the description/name/status.
    if text.startswith('v') and ' - ' in text:
      parts = text.split(' - ', 2)
      if len(parts) == 3 and parts[2] in self.strings:
        return ' - '.join([parts[0], parts[1], self.strings[parts[2]]])
    matched = re.fullmatch(r'(.+)  \[([^\]]+)\]', text)
    if matched and matched[1] in self.strings:
      return self.strings[matched[1]] + '  [' + self.strings.get(matched[2], matched[2]) + ']'
    matched = re.fullmatch(r'(Refresh|Store):? \((.*)\)', text)
    if matched:
      return self.strings[matched[1]] + ' (' + self.strings.get(matched[2], matched[2]) + ')'
    for prefix in ('Store: ', 'Update: ', 'Disengage to ', 'Install ', 'Scan the QR code, or go to '):
      if text.startswith(prefix):
        tail = text[len(prefix):]
        return self.strings[prefix] + self.strings.get(tail, tail)
    matched = re.fullmatch(r'(-?\d+(?:\.\d+)?) (s|m|km|km/h|mph)', text)
    if matched:
      return matched[1] + ' ' + DISTANCE_UNITS.get(matched[2], self.strings.get(matched[2], matched[2]))
    matched = re.fullmatch(r'(TURN L|TURN R|KEEP L|KEEP R|SHARP L|SHARP R|U-TURN L|U-TURN R|STRAIGHT|ROUNDABOUT|DEST)  (\d+) m', text)
    if matched:
      return self.strings[matched[1]] + '  ' + matched[2] + ' 米'
    matched = re.fullmatch(r'Fork (LEFT|RIGHT|BOTH) (\d+) m - (route unconfirmed|follow route|route consistent|checking route|may be another fork)', text)
    if matched:
      return self.strings['Fork']+' '+self.strings['Fork '+matched[1]]+' '+matched[2]+' 米 - '+self.strings[matched[3]]
    matched = re.fullmatch(r'(Vision lane estimate|Vision lane verified) ([1-5])/([1-5])', text)
    if matched:
      return self.strings[matched[1]]+' '+matched[2]+'/'+matched[3]
    return None

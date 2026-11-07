"""Failures first: settings missing; compiled SP keys shadowed by plugin-local
copies; speed labels use the wrong units; import/enable changes live controls;
page bypasses parked-only host editing. The optional tile is read-only.
"""
import importlib.util
import json
from pathlib import Path
from openpilot.tesla import manifest
from openpilot.tesla.plugin_params import ParamsView

ROOT=Path(__file__).resolve().parents[1]


def test_real_sp_settings_have_one_storage_location_and_valid_ranges():
  data=json.loads((ROOT/'plugin.json').read_text())
  assert data['claims']==[] and data['use']=='offroad'
  assert data['params']=={'XpTurnLaneSettingsEnabled':{'type':'BOOL','default':'0'}}
  fields={s['key']:s for s in data['settings']}
  assert set(fields)=={'LaneTurnDesire','LaneTurnValue','AutoLaneChangeTimer'}
  assert set(fields)<=manifest.compiled_param_keys()
  for label,mph in fields['LaneTurnValue']['choices']:
    assert 0<mph<=20
    assert abs(float(label.split()[0])-mph*1.609344)<.06
  assert dict((v,k) for k,v in fields['AutoLaneChangeTimer']['choices'])[2]=='0.5 s'
  class Core:
    def __init__(self):self.data={'LaneTurnDesire':True,'LaneTurnValue':19.,'AutoLaneChangeTimer':2}
    def get(self,key,**kw):return self.data.get(key)
    def put(self,key,v,**kw):self.data[key]=v
  core=Core();before=dict(core.data);view=ParamsView(core,data['params'])
  assert view.get('LaneTurnValue')==19. and core.data==before
  view.put('LaneTurnValue',18);view.put('AutoLaneChangeTimer',3)
  assert core.data['LaneTurnValue']==18 and core.data['AutoLaneChangeTimer']==3


def test_entry_has_no_control_or_process_hooks():
  spec=importlib.util.spec_from_file_location('turn_lane_settings_contract',ROOT/'plugin.py')
  mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
  assert set(mod.TurnLaneSettings.__dict__)<= {'__module__','__doc__'}
  source=(ROOT/'ui.py').read_text()
  assert 'SettingRow' in source and 'show="offroad"' in source
  assert '.put(' not in source and '.put_bool(' not in source

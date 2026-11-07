"""Failures: conflict still emits up ticks; nav runtime never exposes fork evidence."""
from types import SimpleNamespace as N
from auto_speed.controller import AutoSpeedController
from navassist.runtime import NavigationRuntime
from navassist.settings import NavSettings
from navassist.hud import present_hud


def test_conflict_stops_increase_but_retains_decrease_and_driver_override():
  c=AutoSpeedController(configured=True)
  out=N(cruiseState=N(enabled=True,speedCluster=40/3.6),brakePressed=False)
  s=N(out=out,tesla_speed_limit_assist_enabled=True,tesla_speed_limit_target_valid=True,
      tesla_speed_limit_target=60/3.6,tesla_speed_units='KPH',tesla_map_conflict=True,
      tesla_speed_button_template=bytes([1,0,0,0,0,0,0,0]),tesla_speed_button_template_nanos=1,
      tesla_manual_speed_adjustment_counter=0)
  cc=N(enabled=True,cruiseControl=N(cancel=False))
  assert c.update(cc,s,1)==[]
  assert c.update(cc,s,600_000_001)==[]
  s.tesla_speed_limit_target=30/3.6;s.tesla_speed_button_template_nanos=700_000_001
  assert c.update(cc,s,700_000_001)==[]
  assert c.update(cc,s,1_300_000_001)[0].dat[3]&63==63
  s.tesla_manual_speed_adjustment_counter=1
  assert c.update(cc,s,1_400_000_001)==[] and c.manual_override_active


def test_runtime_keeps_missing_map_advisory_and_disable_clears_it():
  r=NavigationRuntime(NavSettings(enabled=False))
  result=r.tick(None,None,0,N(vEgo=0),N(latActive=False),10)
  assert result['nav']['branchEvidence']['state']=='UNAVAILABLE'
  assert not result['intent'].get('signalRequested')
  nav=dict(valid=True,branchEvidence=dict(message='Fork RIGHT 200 m - checking route'))
  assert present_hud(nav,{}, {})['branch_message']==nav['branchEvidence']['message']


def test_expired_fused_source_stops_all_ticks_without_clearing_driver_override():
  c=AutoSpeedController(configured=True)
  s=N(out=N(cruiseState=N(enabled=True,speedCluster=40/3.6),brakePressed=False),
      tesla_speed_limit_assist_enabled=True,tesla_speed_limit_target_valid=True,
      tesla_speed_limit_target=60/3.6,tesla_fused_limit_fresh=False,
      tesla_speed_button_template=bytes([1,0,0,0,0,0,0,0]),tesla_speed_button_template_nanos=1)
  cc=N(enabled=True,cruiseControl=N(cancel=False))
  c.update(cc,s,1)
  assert c.update(cc,s,600_000_001)==[]

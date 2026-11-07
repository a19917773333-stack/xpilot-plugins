

def test_sender_diagnostics_exposes_missing_template_without_sending():
  from types import SimpleNamespace as N
  from navassist.turnsignal import TurnSignalController
  sender=TurnSignalController();intent=dict(valid=True,signalRequested=True,direction='left',sessionId='s',requestId=1)
  car=N(leftBlinker=False,rightBlinker=False,brakePressed=False);cc=N(latActive=True)
  frames=sender.update(intent,car,cc,1_000_000_000,enabled=True)
  assert not frames
  assert sender.diagnostics(intent,car,cc,1_000_000_000,enabled=True,frames=frames)['reason']=='templateMissing'

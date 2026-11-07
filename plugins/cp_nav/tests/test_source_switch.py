"""Failures first: a persisted old CP source flag reactivates CP when the user
selects TesNav. Exercise the real navassist main() startup selection, with IO
factories stopped before any socket, Params store or managed service is opened.
"""
from types import SimpleNamespace as N


def test_selecting_tesnav_does_not_reenter_the_retired_shared_cp_profile(monkeypatch):
 from navassist import process,cpnetwork
 seen=[]
 class StopStartup(Exception):pass
 def stop(which):
  def factory(*a,**kw):seen.append(which);raise StopStartup()
  return factory
 monkeypatch.setattr(process,'Params',lambda:object())
 monkeypatch.setattr(process.plugins,'view',lambda p:N(get=lambda *a,**k:'1'))
 monkeypatch.setattr(process,'read_settings',lambda p:N())
 monkeypatch.setattr(process,'NavigationRuntime',lambda s:None)
 monkeypatch.setattr(process,'NavAssistStore',lambda **kw:object())
 monkeypatch.setattr(process.messaging,'SubMaster',lambda *a:N())
 monkeypatch.setattr(process.messaging,'sub_sock',lambda *a,**kw:None)
 monkeypatch.setattr(process.messaging,'PubMaster',lambda *a:None)
 monkeypatch.setattr(process,'NavigationTransports',stop('tesnav'))
 monkeypatch.setattr(cpnetwork,'CPTransports',stop('retired_cp_source'))
 try:process.main()
 except StopStartup:pass
 assert seen==['tesnav']

"""Real socket regressions for reusable, latency-sensitive camera transport."""
import http.client
import socket
import threading
from phone_vision.bridge import BridgeServer, Handler


class Frames:
  def __init__(self):self.calls=0
  def issue(self, **kwargs):
    self.calls+=1
    return {'frame_id':self.calls}


def serve():
  server=BridgeServer(('127.0.0.1',0),'a'*32,Frames())
  threading.Thread(target=server.serve_forever,daemon=True).start()
  return server


def test_successes_reuse_connection_and_keep_response_framing(monkeypatch):
  options=[];setup=Handler.setup
  def observed(handler):
    setup(handler)
    options.append(handler.connection.getsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY))
  monkeypatch.setattr(Handler,'setup',observed)
  server=serve();client=http.client.HTTPConnection(*server.server_address,timeout=2)
  try:
    headers={'Authorization':'Bearer '+'a'*32}
    client.request('GET','/v1/frame',headers=headers);response=client.getresponse()
    assert response.version==11 and response.status==200
    assert b'"frame_id": 1' in response.read();first_socket=client.sock
    client.request('GET','/v1/frame',headers=headers);response=client.getresponse()
    assert response.status==200 and b'"frame_id": 2' in response.read()
    assert client.sock is first_socket and len(options)==1 and options[0]!=0
  finally:client.close();server.shutdown();server.server_close()


def test_unauthorized_connection_is_closed_without_camera_capture():
  server=serve();client=http.client.HTTPConnection(*server.server_address,timeout=2)
  try:
    client.request('GET','/v1/frame');response=client.getresponse()
    assert response.status==401 and response.will_close
    response.read();assert server.store.calls==0
  finally:client.close();server.shutdown();server.server_close()


def test_unread_oversized_body_closes_connection_before_any_next_request():
  server=serve();client=http.client.HTTPConnection(*server.server_address,timeout=2)
  try:
    client.request('POST','/v1/observation',body=b'x'*8193,headers={'Authorization':'Bearer '+'a'*32})
    response=client.getresponse()
    assert response.status==400 and response.will_close
    assert b'body_size' in response.read()
    client.request('GET','/v1/frame',headers={'Authorization':'Bearer '+'a'*32})
    response=client.getresponse();assert response.status==200
    assert b'"frame_id": 1' in response.read()
  finally:client.close();server.shutdown();server.server_close()


def test_compression_is_lossless_opt_in_and_response_framing_stays_reusable():
  import gzip
  import json
  server=serve();server.store.issue=lambda **kwargs:{'jpeg_b64':'abcdef0123456789'*4096,'frame_id':7}
  client=http.client.HTTPConnection(*server.server_address,timeout=2)
  try:
    headers={'Authorization':'Bearer '+'a'*32,'Accept-Encoding':'gzip'}
    # Old apps send Accept-Encoding automatically but cannot read unknown decoded lengths.
    client.request('GET','/v1/frame',headers=headers);response=client.getresponse()
    assert response.getheader('Content-Encoding') is None
    original=response.read();sock=client.sock
    headers['X-Phone-Vision-Encoding']='gzip-v1'
    client.request('GET','/v1/frame',headers=headers);response=client.getresponse()
    assert response.getheader('Content-Encoding')=='gzip'
    packed=response.read();assert len(packed)==int(response.getheader('Content-Length'))
    assert gzip.decompress(packed)==original and len(packed)<len(original)
    assert json.loads(gzip.decompress(packed))['frame_id']==7 and client.sock is sock
    headers['Accept-Encoding']='gzip;q=0'
    client.request('GET','/v1/frame',headers=headers);response=client.getresponse()
    assert response.getheader('Content-Encoding') is None and response.read()==original
  finally:client.close();server.shutdown();server.server_close()


def test_tiny_ack_and_errors_are_never_compressed():
  server=serve();client=http.client.HTTPConnection(*server.server_address,timeout=2)
  try:
    headers={'Authorization':'Bearer '+'a'*32,'Accept-Encoding':'gzip','X-Phone-Vision-Encoding':'gzip-v1'}
    client.request('GET','/v1/frame',headers=headers);response=client.getresponse()
    assert response.status==200 and response.getheader('Content-Encoding') is None;response.read()
    client.request('GET','/unknown',headers=headers);response=client.getresponse()
    assert response.status==404 and response.getheader('Content-Encoding') is None;response.read()
  finally:client.close();server.shutdown();server.server_close()


def test_transport_resolution_default_retains_single_camera_640_and_optional_320():
  from phone_vision.bridge import output_frame_size
  assert output_frame_size(1928,1208)==(640,401)
  assert output_frame_size(1928,1208,320)==(320,200)
  assert output_frame_size(1928,1208,960)==(960,601)

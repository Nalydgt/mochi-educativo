"""Exercise transport failures without opening SSH or touching private settings."""
import ast
import base64
from types import SimpleNamespace

import pytest

from nas import NAS


class Channel:
    def __init__(self, output=(), error=(), status=0, running=False):
        self.output=list(output)
        self.error=list(error)
        self.status=status
        self.running=running
        self.closed=False
        self.eof_sent=False

    def shutdown_write(self):self.eof_sent=True
    def recv_ready(self):return bool(self.output) and not self.error
    def recv_stderr_ready(self):return bool(self.error)
    def recv(self, size):return self.output.pop(0)
    def recv_stderr(self, size):return self.error.pop(0)
    def exit_status_ready(self):return not self.running and not self.output and not self.error
    def recv_exit_status(self):return self.status
    def close(self):self.closed=True


class Stream:
    def __init__(self, channel):
        self.channel=channel
        self.closed=False
        self.source=None

    def write(self, source):self.source=source
    def close(self):self.closed=True


def transport(channel):
    nas=NAS.__new__(NAS)
    streams=tuple(Stream(channel) for _ in range(3))
    nas.client=SimpleNamespace(exec_command=lambda *args,**kwargs:streams)
    return nas,streams


def test_ssh_drains_stderr_before_waiting_for_stdout_and_preserves_utf8():
    # stdout stays blocked until stderr drains, as with a full SSH window.
    channel=Channel(output=(b'{"text":"Espa\xc3',b'\xb1a"}'),error=(b'x'*65536,)*40)
    nas,streams=transport(channel)
    assert nas.python('print("España")')=='{"text":"España"}'
    assert streams[0].source=='print("España")'
    assert channel.eof_sent and channel.closed
    assert all(stream.closed for stream in streams)


def test_ssh_failure_reports_stderr_and_closes_the_channel():
    channel=Channel(output=(b'partial result',),error=(b'x'*2000+b' useful error',),status=1)
    nas,streams=transport(channel)
    with pytest.raises(RuntimeError,match='useful error') as failure:
        nas.python('raise RuntimeError()')
    assert len(str(failure.value))<1250
    assert channel.closed and all(stream.closed for stream in streams)


def test_ssh_deadline_closes_a_channel_that_never_exits(monkeypatch):
    channel=Channel(running=True)
    nas,streams=transport(channel)
    ticks=iter((0,1,2,3))
    monkeypatch.setattr('nas.time.monotonic',lambda:next(ticks))
    monkeypatch.setattr('nas.time.sleep',lambda seconds:None)
    with pytest.raises(TimeoutError,match='deadline'):
        nas.python('while True: pass',timeout=2)
    assert channel.closed and all(stream.closed for stream in streams)


def test_failed_connection_closes_the_ssh_client(monkeypatch):
    closed=[]
    def fail(*args,**kwargs):raise OSError('connection failed')
    client=SimpleNamespace(load_host_keys=lambda path:None,
                           set_missing_host_key_policy=lambda policy:None,
                           connect=fail,close=lambda:closed.append(True))
    monkeypatch.setattr('nas.paramiko.SSHClient',lambda:client)
    with pytest.raises(OSError,match='connection failed'):
        NAS({'host':'unused','user':'unused','identity':'unused'})
    assert closed==[True]


def container_response(monkeypatch, output):
    nas=NAS.__new__(NAS)
    def execute(source,timeout):
        compile(source,'remote-container','exec')
        assignments={node.targets[0].id:ast.literal_eval(node.value)
                     for node in ast.parse(source).body if isinstance(node,ast.Assign)}
        command=base64.b64decode(assignments['COMMAND']).decode()
        assert assignments['MARKER'] in command
        assert timeout==145
        return output(assignments['MARKER'])
    monkeypatch.setattr(nas,'python',execute)
    return nas


def test_container_only_removes_its_own_complete_success_marker(monkeypatch):
    nas=container_response(monkeypatch,lambda marker:'MOCHI_EXIT=0\r\nresult\r\n\r\n'+marker+'0\r\n')
    assert nas.container('unused','unused','printf result')=='MOCHI_EXIT=0\nresult'


@pytest.mark.parametrize('output',[
    lambda marker:'MOCHI_EXIT=0\n',
    lambda marker:'printed '+marker+'0\n',
    lambda marker:marker+'01\n',
    lambda marker:marker+'1\n',
    lambda marker:marker+'0\nextra output',
])
def test_container_rejects_missing_partial_or_failed_exit_markers(monkeypatch,output):
    nas=container_response(monkeypatch,output)
    with pytest.raises(RuntimeError,match='did not succeed'):
        nas.container('unused','unused','exit 1')

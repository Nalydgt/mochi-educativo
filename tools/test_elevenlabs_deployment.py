"""Provider activation must preserve the shared data and VPN configuration."""
from copy import deepcopy
import importlib.util
from pathlib import Path

import pytest


def module(name, file):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(file))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


deployment = module('elevenlabs_deployment', 'Deploy-MochiElevenLabs.py')
publisher = module('online_publisher', 'Publish-MochiOnline.py')


def test_switch_preserves_vpn_network_volumes_models_and_device_credentials():
    current = {'services':{'mochi':{
        'environment':{'MOCHI_TOKEN':'device-key', 'MOCHI_NATIVE_VOICE_PROFILE':'old-profile',
            'HERMES_API_KEY':'hermes-key', 'ELEVENLABS_API_KEY':'old-inline-key'},
        'volumes':['/home/admin/old:/app:ro', 'data:/data', '/profile:/profile:ro', '/shared:/shared'],
        'network_mode':'service:tailscale'}, 'tailscale':{'volumes':['vpn:/var/lib/tailscale']}},
        'volumes':{'data':{'external':True}, 'vpn':{'external':True}}}
    before = deepcopy(current)
    selected = deployment.build_config(current, {'code_remote':'/new', 'key_remote':'/private/api.key'},
        {'voice_id':'new-clone', 'source_revision':'reference-hash'})
    assert current == before
    service = selected['services']['mochi']
    assert service['network_mode'] == current['services']['mochi']['network_mode']
    assert selected['services']['tailscale'] == current['services']['tailscale']
    assert selected['volumes'] == current['volumes']
    assert service['volumes'] == ['/new:/app:ro', 'data:/data', '/profile:/profile:ro',
        '/shared:/shared', '/private/api.key:/run/secrets/elevenlabs-api.key:ro']
    env = service['environment']
    assert env['MOCHI_TOKEN'] == 'device-key' and env['HERMES_API_KEY'] == 'hermes-key'
    assert env['MOCHI_NATIVE_VOICE_PROFILE'] == 'old-profile'
    assert 'ELEVENLABS_API_KEY' not in env
    assert env['MOCHI_VOICE_PROVIDER'] == 'elevenlabs'


def test_activation_refuses_suspended_storage_before_any_application_change(tmp_path, monkeypatch):
    class NAS:
        def config(self, name): raise AssertionError('Suspended storage must not be read or modified')
    monkeypatch.setattr(deployment, 'pool_status', lambda nas:[{'name':'Prueba1','status':'SUSPENDED','healthy':False}])
    with pytest.raises(RuntimeError, match='not healthy'):
        deployment.activate(NAS(), {}, {'voice_id':'v','source_revision':'r'},
            {'voice_id':'v','source_revision':'r'}, tmp_path/'state.json')


def test_failed_activation_restores_previous_config_and_keeps_data_volumes(tmp_path, monkeypatch):
    previous = {'services':{'mochi':{'environment':{'HERMES_API_KEY':'retained'},
        'volumes':['/old:/app:ro','data:/data','memory:/shared']}}, 'volumes':{'data':{},'memory':{}}}
    changes = []
    class NAS:
        def config(self, name): return previous
        def upload(self, source, destination): assert source.is_file()
        def update(self, name, config): changes.append(deepcopy(config)); return 'updated'
    monkeypatch.setattr(deployment, 'ROOT', tmp_path)
    monkeypatch.setattr(deployment, 'pool_status', lambda nas:[{'status':'ONLINE','healthy':True}])
    def fail(*args): raise TimeoutError('synthetic health failure')
    monkeypatch.setattr(deployment, 'verify_gateway', fail)
    with pytest.raises(TimeoutError, match='synthetic'):
        deployment.activate(NAS(), {}, {'voice_id':'v','source_revision':'r'},
            {'voice_id':'v','source_revision':'r','code_remote':'/new','key_remote':'/key'}, tmp_path/'state.json')
    assert len(changes) == 2 and changes[-1] == previous
    assert changes[0]['volumes'] == previous['volumes']
    assert not (tmp_path/'state.json').exists()


def test_online_publisher_uses_real_embedded_version_and_rejects_other_app(tmp_path):
    data = bytearray(256); data[0] = 0xe9; data[32:36] = b'\x32\x54\xcd\xab'
    data[48:54] = b'0.11.4'; data[80:85] = b'mochi'
    image = tmp_path/'firmware.bin'; image.write_bytes(data)
    assert publisher.image_version(image)[0] == '0.11.4'
    data[80:85] = b'other'; image.write_bytes(data)
    with pytest.raises(ValueError, match='Mochi'):
        publisher.image_version(image)

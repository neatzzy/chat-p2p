import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from rendezvous_connection import RendezvousConnection


class DummyRendezvous(RendezvousConnection):
    async def _send_and_receive(self, message):
        # simulate register/discover responses
        if message.get('type') == 'REGISTER':
            return {'status': 'OK'}
        if message.get('type') == 'DISCOVER':
            return {'status': 'OK', 'peers': [{'ip': '1.2.3.4', 'port': 8080, 'name': 'p', 'namespace': 'CIC'}]}
        return {'status': 'OK'}


@pytest.mark.asyncio
async def test_register_and_discover(monkeypatch):
    rz = DummyRendezvous()
    # register should return True
    ok = await rz.register()
    assert ok is True
    peers = await rz.discover('*')
    assert isinstance(peers, list)
    assert peers and peers[0]['name'] == 'p'

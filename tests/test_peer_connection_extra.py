import sys
from pathlib import Path
import asyncio
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from peer_connection import PeerConnection
from state import PeerInfo

class DummyPC(PeerConnection):
    def __init__(self, peer_info):
        super().__init__(peer_info)
        self.msgs = []
    async def send_message(self, message):
        self.msgs.append(message)

async def test_send_bye_and_close_calls_send_message():
    peer_info = PeerInfo(ip='1.2.3.4', port=1111, name='x', namespace='CIC')
    pc = DummyPC(peer_info)
    # ensure close won't fail
    await pc.send_bye_and_close()
    # should have attempted to send BYE
    assert any(m['type'] == 'BYE' for m in pc.msgs)

def test_rtt_samples_and_average():
    peer_info = PeerInfo(ip='1.2.3.4', port=1111, name='x', namespace='CIC')
    pc = PeerConnection(peer_info)
    assert pc.get_average_rtt() == 0.0
    pc.add_rtt_sample(0.1)
    pc.add_rtt_sample(0.2)
    avg = pc.get_average_rtt()
    assert avg > 0


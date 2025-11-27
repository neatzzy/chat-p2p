import sys
from pathlib import Path
import asyncio
import types
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from p2p_client import P2PClient

class DummyConn:
    def __init__(self):
        self.sent = []
    async def send_message(self, message):
        self.sent.append(message)

class DummyRouter:
    def __init__(self):
        self.published = []
    async def handle_outbound_pub(self, pub_message, active_connections):
        self.published.append((pub_message, dict(active_connections)))

async def test_send_direct_message_schedules_in_loop():
    client = P2PClient()
    # make get_event_loop raise so fallback uses asyncio.create_task in running loop
    client.get_event_loop = lambda: (_ for _ in ()).throw(Exception('no loop'))

    # add dummy connection
    conn = DummyConn()
    client.active_connections['peer1'] = conn

    # call sync method from within async test
    client.send_direct_message('peer1', 'hello')
    # let loop run tasks
    await asyncio.sleep(0.01)
    assert len(conn.sent) == 1
    assert conn.sent[0]['payload'] == 'hello'

async def test_publish_message_schedules_router_call():
    client = P2PClient()
    client.get_event_loop = lambda: (_ for _ in ()).throw(Exception('no loop'))
    router = DummyRouter()
    client.router = router
    client.active_connections = {'peer1': object()}

    client.publish_message('CIC', 'broadcast')
    await asyncio.sleep(0.01)
    assert len(router.published) == 1
    pub_message, active = router.published[0]
    assert pub_message['payload'] == 'broadcast'

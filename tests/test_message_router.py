import asyncio
import pytest
import sys
from pathlib import Path
# Ensure src is on sys.path for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from message_router import MessageRouter

class DummyConn:
    def __init__(self):
        self.sent = []
    async def send_message(self, message):
        self.sent.append(message)

@pytest.mark.asyncio
async def test_handle_outbound_pub_sends_to_matching_connections():
    router = MessageRouter()
    conn1 = DummyConn()
    conn1.peer_info = type('P', (), {'namespace': 'CIC'})
    conn2 = DummyConn()
    conn2.peer_info = type('P', (), {'namespace': 'OTHER'})

    active = {
        'peer1': conn1,
        'peer2': conn2
    }

    pub_msg = {
        'type': 'PUB',
        'msg_id': 'p1',
        'src': 'alice@CIC',
        'dst': 'CIC',
        'payload': 'hi',
        'ttl': 1
    }

    await router.handle_outbound_pub(pub_msg, active)

    assert len(conn1.sent) == 1
    assert conn1.sent[0]['type'] == 'PUB'
    assert len(conn2.sent) == 0

@pytest.mark.asyncio
async def test_send_unicast_creates_pending_ack():
    router = MessageRouter()
    conn = DummyConn()
    conn.peer_info = type('P', (), {'namespace': 'CIC'})
    active = {'peer1': conn}

    # attach connection to router
    router.connections = active

    await router.send_unicast('peer1', 'hello', require_ack=True)

    # there should be exactly one pending ack task
    assert len(router.pending_acks) == 1
    # cancel tasks to clean up
    for t in list(router.pending_acks.values()):
        t.cancel()

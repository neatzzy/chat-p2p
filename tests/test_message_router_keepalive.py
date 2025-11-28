import asyncio
import time
import pytest

from message_router import MessageRouter
from state import LOCAL_STATE

class DummyConn:
    def __init__(self, peer_id):
        class PI:
            pass
        self.peer_info = PI()
        self.peer_info.peer_id = peer_id
        self.sent = []
    async def send_message(self, message):
        self.sent.append(message)

class DummyKeepAlive:
    def __init__(self):
        self.called_with = None
    def handle_incoming_pong(self, message):
        self.called_with = message

@pytest.mark.asyncio
async def test_ping_triggers_send_pong():
    conn = DummyConn('alice@CIC')
    router = MessageRouter(connections={ 'alice@CIC': conn }, keep_alive=None)

    msg = { 'type': 'PING', 'msg_id': 'm1', 'src': 'alice@CIC', 'timestamp': time.time(), 'ttl': 1 }
    await router.handle_incoming_message(conn, msg)

    # after handling PING, router should have sent a PONG via connection
    assert len(conn.sent) == 1
    sent_msg = conn.sent[0]
    assert sent_msg['type'] == 'PONG'
    assert sent_msg['msg_id'] == 'm1'
    assert sent_msg['dst'] == 'alice@CIC'

@pytest.mark.asyncio
async def test_pong_calls_keepalive_and_adds_rtt():
    conn = DummyConn('bob@CIC')
    keep = DummyKeepAlive()
    router = MessageRouter(connections={ 'bob@CIC': conn }, keep_alive=keep)

    # stub add_rtt_sample on connection
    called = {}
    def add_rtt_sample(rtt):
        called['rtt'] = rtt
    conn.add_rtt_sample = add_rtt_sample

    ts = time.time() - 0.05
    msg = { 'type': 'PONG', 'msg_id': 'm2', 'src': 'bob@CIC', 'timestamp': ts, 'ttl': 1 }

    await router.handle_incoming_message(conn, msg)

    assert keep.called_with is not None
    assert keep.called_with['msg_id'] == 'm2'
    # RTT was added
    assert 'rtt' in called
    assert called['rtt'] >= 0

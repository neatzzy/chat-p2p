import time
import pytest
import asyncio

from keep_alive import KeepAliveManager

class DummyConn:
    def __init__(self, peer_id):
        class PI: pass
        self.peer_info = PI()
        self.peer_info.peer_id = peer_id
        self.sent = []
    async def send_message(self, message):
        self.sent.append(message)

@pytest.mark.asyncio
async def test_send_ping_populates_pending(monkeypatch):
    # control time
    base = 1000.0
    monkeypatch.setattr(time, 'time', lambda: base)

    conn = DummyConn('peer1@CIC')
    ka = KeepAliveManager({'peer1@CIC': conn})

    await ka.send_ping()

    assert 'peer1@CIC' in ka.pending_pings
    msg_id, ts = ka.pending_pings['peer1@CIC']
    assert isinstance(msg_id, str)
    assert ts == base
    # connection should have received one send_message
    assert len(conn.sent) == 1
    sent = conn.sent[0]
    assert sent['type'] == 'PING'
    # O campo `src` deve ser a identidade local configurada em `LOCAL_STATE`
    from state import LOCAL_STATE
    assert sent['src'] == LOCAL_STATE.peer_id

def test_handle_incoming_pong_pops_pending(monkeypatch):
    ka = KeepAliveManager({})
    peer = 'peer2@CIC'
    ka.pending_pings[peer] = ('m1', 100.0)
    monkeypatch.setattr(time, 'time', lambda: 100.12)

    ka.handle_incoming_pong({'src': peer})

    assert peer not in ka.pending_pings

import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from keep_alive import KeepAliveManager


class DummyConn:
    def __init__(self):
        self.sent = []
    async def send_message(self, message):
        self.sent.append(message)


@pytest.mark.asyncio
async def test_send_ping_registers_pending_ping():
    active = {'peer1': DummyConn()}
    kam = KeepAliveManager(active)
    # ensure pending empty
    assert kam.pending_pings == {}
    await kam.send_ping()
    assert 'peer1' in kam.pending_pings

def test_handle_incoming_pong_no_pending():
    kam = KeepAliveManager({})
    # call with message from unknown peer - should not raise
    kam.handle_incoming_pong({'src': 'unknown', 'msg_id': 'm'})

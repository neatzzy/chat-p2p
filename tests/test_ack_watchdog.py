import asyncio
import pytest

from message_router import MessageRouter
from config import ProtocolConfig
import peer_table


class FakeConnection:
    def __init__(self):
        self.sent = []

    async def send_message(self, message):
        # Store a shallow copy to avoid mutation issues
        self.sent.append(dict(message))


@pytest.mark.asyncio
async def test_ack_watchdog_retransmits_and_registers_failure(monkeypatch):
    # Speed up the watchdog timeout
    monkeypatch.setattr(ProtocolConfig, 'ACK_TIMEOUT_SEC', 0.01)

    fake = FakeConnection()
    router = MessageRouter(connections={'bob@CIC': fake})

    calls = []
    monkeypatch.setattr(peer_table.PEER_MANAGER, 'register_connection_failure', lambda peer_id: calls.append(peer_id))

    # Send a unicast that requires ACK; peer will not reply
    await router.send_unicast('bob@CIC', 'hello', require_ack=True)

    # Wait until watchdog task completes and cleans pending_acks
    for _ in range(1000):
        if not router.pending_acks:
            break
        await asyncio.sleep(0.01)
    else:
        pytest.fail('ACK watchdog did not complete in time')

    # Initial send + 3 retransmits (max_retries in code) = 4
    assert len(fake.sent) == 4
    assert calls == ['bob@CIC']


@pytest.mark.asyncio
async def test_ack_watchdog_stops_on_ack(monkeypatch):
    # Larger timeout so we can inject ACK before first timeout
    monkeypatch.setattr(ProtocolConfig, 'ACK_TIMEOUT_SEC', 0.05)

    fake = FakeConnection()
    router = MessageRouter(connections={'bob@CIC': fake})

    calls = []
    monkeypatch.setattr(peer_table.PEER_MANAGER, 'register_connection_failure', lambda peer_id: calls.append(peer_id))

    await router.send_unicast('bob@CIC', 'hello', require_ack=True)

    # Allow initial send to happen
    await asyncio.sleep(0.01)

    assert fake.sent, 'no message was sent'
    msg_id = fake.sent[0]['msg_id']

    # Simulate ACK arrival
    await router.handle_incoming_message(fake, {'type': 'ACK', 'msg_id': msg_id, 'src': 'bob@CIC'})

    # Wait for watchdog to clear
    for _ in range(200):
        if not router.pending_acks:
            break
        await asyncio.sleep(0.01)
    else:
        pytest.fail('ACK watchdog did not stop after receiving ACK')

    # Only the initial send should have occurred
    assert len(fake.sent) == 1
    assert calls == []

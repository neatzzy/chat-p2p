import asyncio
import json
import pytest
import sys
from pathlib import Path
# Ensure src is on sys.path for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from state import PeerInfo
from peer_connection import PeerConnection
from config import ProtocolConfig


def test_encode_decode_roundtrip():
    peer_info = PeerInfo(ip='127.0.0.1', port=9000, name='bob', namespace='CIC')
    pc = PeerConnection(peer_info)

    message = {
        "type": "SEND",
        "msg_id": "m1",
        "src": "alice@CIC",
        "dst": "bob@CIC",
        "payload": "hello",
        "require_ack": True,
        "ttl": ProtocolConfig.TTL
    }

    encoded = pc._encode_message(message)
    # Ensure encoded ends with delimiter
    assert encoded.endswith(ProtocolConfig.MESSAGE_DELIMITER)

    decoded = pc._decode_message(encoded)
    assert decoded == message


@pytest.mark.asyncio
async def test_send_message_no_writer_just_logs():
    peer_info = PeerInfo(ip='127.0.0.1', port=9001, name='carol', namespace='CIC')
    pc = PeerConnection(peer_info)
    # No writer configured; send_message should simply return without exception
    await pc.send_message({"type": "SEND", "msg_id": "x", "src": "a@CIC", "dst": "c@CIC", "payload": "x"})

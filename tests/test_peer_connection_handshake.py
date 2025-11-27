import sys
from pathlib import Path
import asyncio
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from peer_connection import PeerConnection
from state import PeerInfo, LOCAL_STATE
from config import ProtocolConfig


async def _server_handler(reader, writer):
    # create PeerConnection on server side and perform responder handshake
    peer_info = PeerInfo(ip='127.0.0.1', port=writer.get_extra_info('peername')[1], name='remote', namespace='CIC')
    pc = PeerConnection(peer_info, reader, writer)
    # handle handshake on server side
    ok = await pc.do_handshake(is_initiator=False)
    # keep reader open a bit
    await asyncio.sleep(0.01)
    return ok


async def test_handshake_initiator_and_responder():
    # update local id
    LOCAL_STATE.peer_id = 'local@CIC'

    server = await asyncio.start_server(_server_handler, '127.0.0.1', 0)
    addr = server.sockets[0].getsockname()
    host, port = addr[0], addr[1]

    # client side connect
    reader, writer = await asyncio.open_connection(host, port)

    client_peer = PeerInfo(ip=host, port=port, name='client', namespace='CIC')
    client_pc = PeerConnection(client_peer, reader, writer)

    # run initiator handshake
    ok_client = await client_pc.do_handshake(is_initiator=True)

    server.close()
    await server.wait_closed()

    assert ok_client is True

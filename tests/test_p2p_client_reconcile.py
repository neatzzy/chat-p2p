import sys
from pathlib import Path
import asyncio
import types
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from p2p_client import P2PClient
from state import PeerInfo, LOCAL_STATE


async def test_reconcile_success_and_failure(monkeypatch):
    client = P2PClient()

    # create two peer infos: one successful, one failing
    p_success = PeerInfo(ip='127.0.0.1', port=9001, name='suc', namespace='CIC')
    p_fail = PeerInfo(ip='127.0.0.1', port=9002, name='fail', namespace='CIC')

    # ensure they are not the local peer
    LOCAL_STATE.peer_id = 'local@CIC'

    # monkeypatch PEER_MANAGER.get_peers_to_connect to return these peers
    import peer_table

    def fake_get_peers_to_connect():
        return [p_success, p_fail]

    monkeypatch.setattr(peer_table.PEER_MANAGER, 'get_peers_to_connect', fake_get_peers_to_connect)

    # flags to record calls
    calls = {'success': [], 'fail': []}

    def fake_register_success(pid):
        calls['success'].append(pid)

    def fake_register_fail(pid):
        calls['fail'].append(pid)

    monkeypatch.setattr(peer_table.PEER_MANAGER, 'register_successful_connection', fake_register_success)
    monkeypatch.setattr(peer_table.PEER_MANAGER, 'register_connection_failure', fake_register_fail)

    # mock create_outbound_connection: succeed for p_success, fail for p_fail
    import peer_connection

    async def fake_create_outbound_connection(peer_info):
        if peer_info.name == 'suc':
            import types
            return types.SimpleNamespace(peer_info=peer_info)
        return None

    monkeypatch.setattr(peer_connection, 'create_outbound_connection', fake_create_outbound_connection)

    # run reconcile
    await client._reconcile_connections()

    # assertions
    assert any('suc@CIC' == pid for pid in calls['success'])
    assert any('fail@CIC' == pid for pid in calls['fail'])

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from peer_table import PeerTableManager


def test_add_peer_and_update():
    pt = PeerTableManager()
    data = {'ip': '10.0.0.1', 'port': 1111, 'name': 'x', 'namespace': 'CIC'}
    pt._table.add_peer(data)
    # the underlying table is in pt._table.peers
    assert 'x@CIC' in pt._table.peers
    # update existing
    data2 = {'ip': '10.0.0.2', 'port': 2222, 'name': 'x', 'namespace': 'CIC'}
    # clear then add to simulate update
    pt._table.peers.clear()
    pt._table.add_peer(data)
    pt._table.add_peer(data2)
    assert pt._table.peers['x@CIC'].ip == '10.0.0.2'

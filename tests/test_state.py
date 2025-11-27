import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from state import LocalPeerState, PeerInfo


def test_local_peer_state_peer_id():
    lp = LocalPeerState(name='alice', namespace='CIC', listen_port=1234)
    assert lp.peer_id == 'alice@CIC'


def test_peerinfo_post_init():
    p = PeerInfo(ip='1.2.3.4', port=9999, name='bob', namespace='CIC')
    assert p.peer_id == 'bob@CIC'
    assert p.ip == '1.2.3.4'

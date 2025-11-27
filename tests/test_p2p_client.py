import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from p2p_client import set_local_identity, P2PClient, LOCAL_STATE


def test_set_local_identity_updates_state():
    set_local_identity('u', 'N', 5555)
    assert LOCAL_STATE.name == 'u'
    assert LOCAL_STATE.namespace == 'N'
    assert LOCAL_STATE.listen_port == 5555


def test_p2pclient_init_has_components():
    client = P2PClient()
    assert hasattr(client, 'keep_alive')
    assert hasattr(client, 'router')

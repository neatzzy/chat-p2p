import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from config import ProtocolConfig, RendezvousConfig


def test_protocol_config_values():
    assert isinstance(ProtocolConfig.ENCODING, str)
    assert ProtocolConfig.MESSAGE_DELIMITER == b"\n"
    assert ProtocolConfig.TTL >= 0


def test_rendezvous_defaults():
    assert isinstance(RendezvousConfig.HOST, str)
    assert isinstance(RendezvousConfig.PORT, int)
    assert RendezvousConfig.REGISTER_REFRESH_INTERVAL_SEC > 0

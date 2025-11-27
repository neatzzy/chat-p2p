import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

import cli


def test_cli_entry_exists():
    assert hasattr(cli, 'cli')

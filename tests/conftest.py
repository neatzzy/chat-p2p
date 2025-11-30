import sys
from pathlib import Path

# Adiciona a pasta `src` ao PYTHONPATH para que os módulos do projeto sejam importáveis nos testes.
ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'src'
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

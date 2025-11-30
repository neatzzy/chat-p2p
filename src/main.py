##### Projeto de Redes 2025.2 #####
#        Desenvolvedores:         #
#   Élvis Miranda 241038700       #
#   Gustavo Alves 241020779       #
#   Pedro Marcinoni 241002396     #
###################################
import sys
import logging

from cli import cli

def setup_logging(level: str = 'INFO') -> None:
    """Configura o logging básico do aplicativo.

    Args:
        level: Nível de log como string (DEBUG, INFO, WARNING, ERROR, CRITICAL).
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format='%(asctime)s %(message)s',
        datefmt='%H:%M:%S'
    )

# Para rodar o programa, no diretório "src", use o comando:
# python main.py start --name <seu_nome> --namespace <seu_namespace>

if __name__ == '__main__':
    try:
        cli()
    except Exception as e:
        # Captura exceções não tratadas durante o setup do CLI
        logging.exception("[MAIN] Erro fatal na inicialização")
        sys.exit(1)
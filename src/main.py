##### Projeto de Redes 2025.2 #####
#        Desenvolvedores:         #
#   Élvis Miranda 241038700       #
#   Gustavo Alves 241020779       #
#   Pedro Marcinoni 241002396     #
###################################
import sys
import logging

from cli import cli

if __name__ == '__main__':
    try:
        cli()
    except Exception as e:
        # Captura exceções não tratadas durante o setup do CLI
        logging.critical(f"Erro fatal na inicialização: {e}")
        sys.exit(1)
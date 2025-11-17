#interface de linha de comando
import click
import asyncio
import sys 
import threading

# from p2p_client import P2PClient, P2P_ORCHESTRATOR, set_local_identity
# from main import setup_logging

@click.group()
def cli():
    """Interface de Linha de Comando para o Cliente P2P."""
    pass

@cli.command()
@click.option('--name', '-n', required=True, help='Nome único do peer (ex: alice).')
@click.option('--namespace', '-ns', required=True, default='CIC', help='Namespace de agrupamento (ex: CIC).')
@click.option('--port', '-p', required=True, type=int, default=7070, help='Porta de escuta do peer (ex: 7070).')
@click.option('--log-level', '-l', default='INFO', help='Nível de log (DEBUG, INFO, WARNING, ERROR).')
def start(name, namespace, port, log_level):
    """Inicia o cliente P2P e o conecta ao rendezvous."""
    click.clear()
    click.echo(f"✨ Iniciando PyP2p como {name}@{namespace} na porta {port}...")

    # Configura a identidade local
    # set_local_identity(name, namespace, port)

    # Configura o logging
    # setup_logging(log_level)

    # Inicializa o Orquestrador P2P
    # client = P2PClient()

    # Inicia o loop assíncrono em uma thread separada
    # asyncio_thread = threading.Thread(target=client.start_async_loop, daemon=True)
    # asyncio_thread.start()

    # Inicia a interface CLI
    # loop_cli_commands(client)

    click.echo("🚀 Cliente P2P iniciado com sucesso! Use '/quit' para sair.")

    command_loop(None)  # Substituir None por client quando descomentado

def command_loop(client):
      """Loop de comandos CLI para interagir com o cliente P2P."""
      while True:
          command = input(">> ")
          handle_client_commands(None, command)  # Substituir None por client quando descomentado

def handle_client_commands(client, raw_command: str):
    """Processa comandos interativos para o cliente P2P."""
    parts = raw_command.strip().split(maxsplit=2)
    command = parts[0].lower()

    if command == '/msg':
        if len(parts) == 3:
            dst_peer_id = parts[1]
            payload = parts[2]
            # client.send_direct_message(dst_peer_id, payload)
            click.echo(f"Enviando SEND para {dst_peer_id}: '{payload}'")
        else:
            click.echo("Uso: /msg <peer_id> <mensagem>")
    elif command == '/peers':
        pass
    elif command == '/pub':
        pass
    elif command == '/conn':
        pass
    elif command == '/rtt':
        pass
    elif command == '/reconnect':
        pass
    elif command == '/log':
        pass
    elif command == '/help':
        click.echo("""Comandos disponíveis:
/msg <peer_id> <mensagem> - Envia uma mensagem direta para o peer especificado.
/peers [* | #namespace] - Descobrir e listar peers.
/pub * <mensagem> - Publica uma mensagem global.
/pub #<namespace> <mensagem> - Publica uma mensagem em um namespace específico.
/conn - Mostrar conexões ativas.
/rtt - Exibe o RTT médio por peer.
/reconnect - Forçar reconciliação de peers.
/log <nível> - Altera o nível de log (DEBUG, INFO, WARNING, ERROR).
/help - Mostra esta mensagem de ajuda.
/quit - Encerra o cliente P2P.""")
    elif command == '/quit':
        click.echo("Encerrando o cliente P2P...")
        # client.stop()
        sys.exit(0)
    else:
        click.echo(f"Comando desconhecido: {command}")

if __name__ == '__main__':
    # python cli.py start --name alice --namespace CIC
    cli()


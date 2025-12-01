#interface de linha de comando
import click
import asyncio
import sys 
import threading
import logging
import time

from p2p_client import P2PClient, set_local_identity
from peer_table import PEER_MANAGER
from rendezvous_connection import RENDEZVOUS_CONNECTION

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

    # Configura a identidade local
    set_local_identity(name, namespace, port)

    from main import setup_logging
    setup_logging(log_level)

    """Inicia o cliente P2P e o conecta ao rendezvous."""
    click.clear()
    # Colored startup message
    click.secho(f"✨ Iniciando PyP2p como {name}@{namespace} na porta {port}...", fg='cyan')

    # Inicializa o Orquestrador P2P
    client = P2PClient()

    # Inicia o loop assíncrono em uma thread separada
    def run_p2p_client():
        client.start(name, namespace, port)
        
    asyncio_thread = threading.Thread(target=run_p2p_client, daemon=True)
    asyncio_thread.start()

    click.secho("🚀 Cliente P2P iniciado com sucesso! Use '/quit' para sair.", fg='green')
    time.sleep(0.75)
    command_loop(client)

def command_loop(client):
    """Loop de comandos CLI para interagir com o cliente P2P."""
    while True:
        command = click.prompt("> ", prompt_suffix='', default='/help', show_default=False)
        handle_client_commands(client, command)

def handle_client_commands(client, raw_command: str):
    """Processa comandos interativos para o cliente P2P."""
    parts = raw_command.strip().split(maxsplit=2)
    command = parts[0].lower()

    if command == '/msg':
        if len(parts) == 3:
            dst_peer_id = parts[1]
            payload = parts[2]
            client.send_direct_message(dst_peer_id, payload)
        else:
            click.secho("[CLI] Uso: /msg <peer_id> <mensagem>", fg='yellow')
    elif command == '/peers':
        if len(parts) == 2:
            namespace = parts[1]
            asyncio.run_coroutine_threadsafe(client.discover_in_namespace(namespace), client.get_event_loop())
            if namespace == '*':
                peers = PEER_MANAGER.get_all_peers()
                click.secho("[CLI] Listando todos os peers:", fg='cyan')
            elif namespace.startswith('#'):
                ns = namespace[1:]
                peers = PEER_MANAGER.get_peers_in_namespace(ns)
                click.secho(f"[CLI] Listando peers no namespace '{ns}':", fg='cyan')
            else:
                click.secho("[CLI] Uso: /peers [* | #namespace]", fg='yellow')
                return
            for peer in peers:
                click.secho(f"- {peer.peer_id}", fg='white')
        else:
            click.echo("[CLI] Uso: /peers [* | #namespace]")
    elif command == '/pub':
        if len(parts) == 3:
            dst = parts[1]
            if dst.startswith('#'):
                dst = dst[1:]
            payload = parts[2]
            client.publish_message(dst, payload)
        else:
            click.secho("[CLI] Uso: /pub * <mensagem> ou /pub #<namespace> <mensagem>", fg='yellow')
    elif command == '/conn':
        if len(parts) == 1:
            connections = client.get_connection_status()
            for conn in connections:
                click.secho(f"- {conn}", fg='white')
            click.secho("[CLI] Listando conexões ativas...", fg='cyan')
        else:
            click.secho("Uso: /conn", fg='yellow')
    elif command == '/rtt':
        if len(parts) == 1:
            rtts = client.get_avg_rtts()
            click.secho("[CLI] Exibindo RTT médio por peer...", fg='cyan')
            for peer_id, rtt in rtts.items():
                click.secho(f"- {peer_id}: {rtt:.2f} ms", fg='white')
        else:
            click.secho("[CLI] Uso: /rtt", fg='yellow')
    elif command == '/reconnect':
        if len(parts) == 1:
            client.reconnect_peers()
            click.secho("[CLI] Forçando reconciliação de peers...", fg='cyan')
        else:
            click.secho("[CLI] Uso: /reconnect", fg='yellow')
    elif command == '/log':
        if len(parts) == 2:
            level = parts[1].upper()
            client.set_log_level(level)
            click.secho(f"[CLI] Nível de log alterado para {level}", fg='cyan')
        else:
            click.secho("[CLI] Uso: /log <nível>", fg='yellow')
    elif command == '/help':
         click.secho("""Comandos disponíveis:
     /msg <peer_id> <mensagem> - Envia uma mensagem direta para o peer especificado.
     /peers [* | #namespace] - Descobrir e listar peers.
     /pub * <mensagem> - Publica uma mensagem global.
     /pub #<namespace> <mensagem> - Publica uma mensagem em um namespace específico.
     /conn - Mostrar conexões ativas.
     /rtt - Exibe o RTT médio por peer.
     /reconnect - Forçar reconciliação de peers.
     /log <nível> - Altera o nível de log (DEBUG, INFO, WARNING, ERROR).
     /help - Mostra esta mensagem de ajuda.
     /quit - Encerra o cliente P2P.""", fg='green')
    elif command == '/quit':
        click.secho("[CLI] Encerrando o cliente P2P...", fg='yellow')
        try:
            future = asyncio.run_coroutine_threadsafe(client.stop(), client.get_event_loop())
            # Espera a corrotina terminar (com timeout para segurança)
            future.result(timeout=10)  # 10 segundos de timeout
        except TimeoutError:
            click.secho("[CLI] Timeout ao encerrar cliente, forçando saída...", fg='red')
        except Exception as e:
            click.secho(f"[CLI] [ERROR] Erro ao encerrar cliente: {e}", fg='red')
        sys.exit(0)

if __name__ == '__main__':
    # python cli.py start --name alice --namespace CIC
    cli()
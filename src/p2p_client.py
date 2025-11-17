# lógica principal (registro, descoberta, reconexão, CLI)
import asyncio
import time
from typing import Optional, Dict, Any

# Importações internas
from config import ProtocolConfig, RendezvousConfig
from state import LOCAL_STATE, PeerInfo
from peer_table import PEER_MANAGER
from rendezvous_connection import RENDEZVOUS_CONNECTION
from peer_connection import create_outbound_connection, PeerConnection

class P2PClient:
  """Orquestrador central do cliente P2P. Gerencia o ciclo de vida da aplicação, tarefas periódicas e reconciliação da rede."""
  def __init__(self):
    self._is_running = False
    self._listener_task: Optional[asyncio.Task] = None
    self._periodic_tasks: Dict[str, asyncio.Task] = {} 
    self.active_connections: Dict[str, Any] = {}
      
  # Ciclo de vida e inicialização

  def start(self, name: str, namespace: str, port: int):
    """Inicia o cliente P2P."""
    set_local_identity(name, namespace, port)
    print(f"Orquestrador iniciado para {LOCAL_STATE.peer_id}")

    self._is_running = True
    try:
      asyncio.run(self._run_async())
    except KeyboardInterrupt:
      print("Interrupção pelo usuário recebida. Encerrando...")
      self.stop()


  async def _run_async(self):
    """Função assíncrona que gerencia o agendamento de tarefas."""
    self._listener_task = asyncio.create_task(self._start_listening_server())
    self._periodic_tasks['register'] = asyncio.create_task(self._periodic_task_runner(self._refresh_register, RendezvousConfig.REGISTER_REFRESH_INTERVAL_SEC))
    self._periodic_tasks['discover'] = asyncio.create_task(self._periodic_task_runner(self._run_discovery_and_reconcile, RendezvousConfig.DISCOVER_INTERVAL_SEC))

    await asyncio.gather(*self._periodic_tasks.values(), return_exceptions=True)

  async def stop(self):
    """Encerra o cliente de forma limpa: unregister, BYE/BYE_OK, e cancela tarefas."""
    self._is_running = False

    print("Encerrando cliente P2P...")

    await RENDEZVOUS_CONNECTION.unregister()

    await self._send_bye_and_close_connections()

    for task in self._periodic_tasks.values():
      task.cancel()
    if self._listener_task:
      self._listener_task.cancel()

    print("Cliente P2P encerrado.")

  # Tarefas periódicas

  async def _periodic_task_runner(self, func, interval: int):
    """Função utilitária para rodar uma função periodicamente."""
    while self._is_running:
      await func()
      await asyncio.sleep(interval)
  
  async def _refresh_register(self):
    """Executa o REGISTER periodicamente."""
    await RENDEZVOUS_CONNECTION.register()

  async def _run_discovery_and_reconcile(self):
    """Executa a descoberta de peers e reconciliação da tabela de peers."""
    print("[Discvery] Iniciando descoberta de peers...")
    peers_list = await RENDEZVOUS_CONNECTION.discover(namespace=LOCAL_STATE.namespace)

    PEER_MANAGER.update_from_discovery(peers_list)

    await self._reconcile_connections()
  
  async def _reconcile_connections(self):
    """Compara a PEER_TABLE com as conexões ativas e inicia novas conexões seguindo a lógica de backoff."""
    peers_to_connect = PEER_MANAGER.get_peers_to_connect()

    for peer_info in peers_to_connect:
      if peer_info.peer_id not in self.active_connections:
        print(f"[Reconcile] Tentando conectar a {peer_info.peer_id}...")

        new_conn = await create_outbound_connection(peer_info)

        if new_conn:
          self.active_connections[peer_info.peer_id] = new_conn
          PEER_MANAGER.register_successful_connection(peer_info.peer_id)
        else:
          PEER_MANAGER.register_connection_failure(peer_info.peer_id)

  # Servidor de escuta e conexões
  async def _start_listening_server(self):
    """Inicia o servidor TCP para conexões de entrada."""
    try:
      server = await asyncio.start_server(
      self._handle_inbound_connection,
      '0.0.0.0',
      LOCAL_STATE.listen_port
      )
      addr = server.sockets[0].getsockname()
      print(f"[PeerServer] Escutando conexões INBOUND em {addr}")

      async with server:
        await server.serve_forever()
    except OSError as e:
      print(f"[PeerServer ERROR] Falha ao iniciar o servidor na porta {LOCAL_STATE.listen_port}: {e}")
      self.stop()

  async def _handle_inbound_connection(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    """Callback chamado quando uma nova conexão INBOUND é aceita. Inicia o Handshake e o Listenter para a conexão."""
    addr = writer.get_extra_info('peername')
    temp_peer_id = f"{addr[0]}:{addr[1]}"

    temp_peer_info = PeerInfo(
      ip=addr[0],
      port=addr[1],
      name="unknown_inbound",
      namespace="inbound",
    )

    print(f"[PeerServer] Conexão INBOUND recebida de {temp_peer_id}. Iniciando handshake...")

    connection = PeerConnection(temp_peer_info, reader, writer)
    if await connection.do_handshake():
      self.active_connections[connection.peer_info.peer_id] = connection
      PEER_MANAGER.register_successful_connection(connection.peer_info.peer_id)
      asyncio.create_task(connection.run_listener())
    else:
      await connection.close()

  async def _send_bye_and_close_connections(self):
    """Envia BYE para todas as conexões ativas e fecha-as."""
    print("Enviando BYE para todas as conexões ativas...")
    close_tasks = []
    for peer_id, connection in self.active_connections.items():
      print(f"Enviando BYE para {peer_id}...")
      close_tasks.append(connection.send_bye_and_close())
    await asyncio.gather(*close_tasks)
    self.active_connections.clear()
    print("Todas as conexões foram encerradas.")
  
  # Funcões para a CLI

  def send_direct_message(self, peer_id: str, message: str):
    """Envia uma mensagem direta para um peer específico."""
    pass

  def publish_message(self, namespace: str, message: str):
    """Publica uma mensagem em um namespace específico."""
    pass

  def get_connection_status(self) -> Dict[str, Any]:
    """Retorna o status atual das conexões ativas."""
    pass

  def get_avg_rtts(self) -> Dict[str, float]:
    """Retorna o RTT médio para cada peer conectado."""
    pass

  def reconnect_peers(self):
    """Força a reconciliação imediata das conexões de peers."""
    pass

  def set_log_level(self, level: str):
    """Define o nível de log para o cliente P2P."""
    pass

P2P_ORCHESTRATOR = P2PClient()

def set_local_identity(name: str, namespace: str, port: int):
  """Define a identidade local do peer."""
  global LOCAL_STATE
  LOCAL_STATE.name = name
  LOCAL_STATE.namespace = namespace
  LOCAL_STATE.listen_port = port
  LOCAL_STATE.peer_id = f"{name}@{namespace}:{port}"
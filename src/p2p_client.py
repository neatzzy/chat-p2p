# lógica principal (registro, descoberta, reconexão, CLI)
import asyncio
import time
import uuid
from typing import Optional, Dict, Any, TYPE_CHECKING

# Importações internas
from config import ProtocolConfig, RendezvousConfig
from state import LOCAL_STATE, PeerInfo
from peer_table import PEER_MANAGER
from rendezvous_connection import RENDEZVOUS_CONNECTION
import logging
if TYPE_CHECKING:
  from peer_connection import PeerConnection
  from keep_alive import KeepAliveManager
  from message_router import MessageRouter

class P2PClient:
  """Orquestrador central do cliente P2P. Gerencia o ciclo de vida da aplicação, tarefas periódicas e reconciliação da rede."""
  def __init__(self):
    self._is_running = False
    self._listener_task: Optional[asyncio.Task] = None
    self._periodic_tasks: Dict[str, asyncio.Task] = {}
    self.active_connections: Dict[str, "PeerConnection"] = {}

    # Lazy import and wiring to avoid circular imports during module import
    from keep_alive import KeepAliveManager
    from message_router import MessageRouter

    self.keep_alive = KeepAliveManager(self.active_connections)
    self.router = MessageRouter(self.active_connections, self.keep_alive)
  # Ciclo de vida e inicialização

  def start(self, name: str, namespace: str, port: int):
    """Inicia o cliente P2P."""
    set_local_identity(name, namespace, port)
    logging.getLogger(__name__).info(f"Orquestrador iniciado para {LOCAL_STATE.peer_id}")

    self._is_running = True
    try:
      asyncio.run(self._run_async())
    except KeyboardInterrupt:
      logging.getLogger(__name__).info("Interrupção pelo usuário recebida. Encerrando...")
      self.stop()

  def get_event_loop(self) -> asyncio.AbstractEventLoop:
    """Retorna o event loop ativo."""
    return self._loop


  async def _run_async(self):
    """Função assíncrona que gerencia o agendamento de tarefas."""
    self._loop = asyncio.get_event_loop()
    self._listener_task = asyncio.create_task(self._start_listening_server())
    self._periodic_tasks['register'] = asyncio.create_task(self._periodic_task_runner(self._refresh_register, RendezvousConfig.REGISTER_REFRESH_INTERVAL_SEC))
    self._periodic_tasks['discover'] = asyncio.create_task(self._periodic_task_runner(self._run_discovery_and_reconcile, RendezvousConfig.DISCOVER_INTERVAL_SEC))
    self._periodic_tasks['keep_alive'] = asyncio.create_task(self._periodic_task_runner(self.keep_alive.send_ping, ProtocolConfig.PING_INTERVAL_SEC))

    await asyncio.gather(*self._periodic_tasks.values(), return_exceptions=True)

  async def stop(self):
    """Encerra o cliente de forma limpa: unregister, BYE/BYE_OK, e cancela tarefas."""
    self._is_running = False

    logging.getLogger(__name__).info("Encerrando cliente P2P...")

    await RENDEZVOUS_CONNECTION.unregister()

    await self._send_bye_and_close_connections()

    for task in self._periodic_tasks.values():
      task.cancel()
    if self._listener_task:
      self._listener_task.cancel()

    logging.getLogger(__name__).info("Cliente P2P encerrado.")

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
    logging.getLogger(__name__).debug("[Discovery] Iniciando descoberta de peers...")
    peers_list = await RENDEZVOUS_CONNECTION.discover('*')

    PEER_MANAGER.update_from_discover(peers_list)

    await self._reconcile_connections()
  
  async def discover_in_namespace(self, namespace: str):
    """Descobre peers em um namespace específico e reconcilia conexões."""
    logging.getLogger(__name__).debug(f"[Discovery] Iniciando descoberta de peers no namespace '{namespace}'...")
    peers_list = await RENDEZVOUS_CONNECTION.discover(namespace)

    PEER_MANAGER.update_from_discover(peers_list)

    await self._reconcile_connections()

  async def _reconcile_connections(self):
    """Compara a PEER_TABLE com as conexões ativas e inicia novas conexões seguindo a lógica de backoff."""
    peers_to_connect = PEER_MANAGER.get_peers_to_connect()

    for peer_info in peers_to_connect:
      if peer_info.peer_id not in self.active_connections and peer_info.peer_id != LOCAL_STATE.peer_id:
        logging.getLogger(__name__).info(f"[Reconcile] Tentando conectar a {peer_info.peer_id}...")

        # Import lazily to avoid circular import at module load time
        from peer_connection import create_outbound_connection

        new_conn = await create_outbound_connection(peer_info)

        if new_conn:
          # Wire router to the new connection so it can forward incoming messages
          try:
            new_conn.router = self.router
          except Exception:
            pass
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
      logging.getLogger(__name__).info(f"[PeerServer] Escutando conexões INBOUND em {addr}")

      async with server:
        await server.serve_forever()
    except OSError as e:
      logging.getLogger(__name__).error(f"[PeerServer ERROR] Falha ao iniciar o servidor na porta {LOCAL_STATE.listen_port}: {e}")
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

    logging.getLogger(__name__).info(f"[PeerServer] Conexão INBOUND recebida de {temp_peer_id}. Iniciando handshake...")

    # Import PeerConnection lazily to avoid circular import at module load time
    from peer_connection import PeerConnection

    connection = PeerConnection(temp_peer_info, reader, writer)
    if await connection.do_handshake(is_initiator=False):
      # Wire router so incoming messages are routed
      try:
        connection.router = self.router
      except Exception:
        pass
      self.active_connections[connection.peer_info.peer_id] = connection
      PEER_MANAGER.register_successful_connection(connection.peer_info.peer_id)
      asyncio.create_task(connection.run_listener())
    else:
      await connection.close()

  async def _send_bye_and_close_connections(self):
    """Envia BYE para todas as conexões ativas e fecha-as."""
    logging.getLogger(__name__).info("Enviando BYE para todas as conexões ativas...")
    close_tasks = []
    for peer_id, connection in self.active_connections.items():
      logging.getLogger(__name__).debug(f"Enviando BYE para {peer_id}...")
      close_tasks.append(connection.send_bye_and_close())
    await asyncio.gather(*close_tasks)
    self.active_connections.clear()
    logging.getLogger(__name__).info("Todas as conexões foram encerradas.")
  
  # Funcões para a CLI

  def _get_msg_id(self) -> str:
    """Gera um ID único para mensagens."""
    return str(uuid.uuid4())

  def send_direct_message(self, dst_peer_id: str, message: str):
    """Envia uma mensagem direta para um peer específico."""
    conn = self.active_connections.get(dst_peer_id)

    if not conn:
      logging.getLogger(__name__).warning(f"[Client ERROR] Conexão para peer_id {dst_peer_id} não encontrada.")
      return
    
    message = {
      "type": "SEND",
      "msg_id": self._get_msg_id(),
      "src": LOCAL_STATE.peer_id,
      "dst": dst_peer_id,
      "payload": message,
      "require_ack": True,
      "ttl": ProtocolConfig.TTL}
    
    # PeerConnection lida com o envio real — agendar na event loop do orquestrador
    try:
      loop = self.get_event_loop()
    except Exception:
      loop = None

    if loop:
      asyncio.run_coroutine_threadsafe(conn.send_message(message), loop)
    else:
      # fallback: try to create a task in current loop (may raise if no loop)
      try:
        asyncio.create_task(conn.send_message(message))
      except RuntimeError:
        logging.getLogger(__name__).warning("[Client ERROR] Nenhum event loop disponível para enviar a mensagem.")
    logging.getLogger(__name__).info(f"[Client] Mensagem SEND enviada para {dst_peer_id}.")

  def publish_message(self, namespace: str, message: str):
    """Publica uma mensagem em um namespace ou globalmente."""
    pub_message = {
      "type": "PUB",
      "msg_id": self._get_msg_id(),
      "src": LOCAL_STATE.peer_id,
      "dst": namespace,
      "payload": message,
      "require_ack": False,
      "ttl": ProtocolConfig.TTL}
    
    # Schedule outbound publish on the orchestrator's event loop
    try:
      loop = self.get_event_loop()
    except Exception:
      loop = None

    if loop:
      asyncio.run_coroutine_threadsafe(self.router.handle_outbound_pub(pub_message, self.active_connections), loop)
    else:
      try:
        asyncio.create_task(self.router.handle_outbound_pub(pub_message, self.active_connections))
      except RuntimeError:
        logging.getLogger(__name__).warning("[Client ERROR] Nenhum event loop disponível para publicar a mensagem.")
    logging.getLogger(__name__).info(f"[Client] Mensagem PUB publicada para o namespace '{namespace}'.")

  def get_connection_status(self) -> Dict[str, Any]:
    """Retorna o status atual das conexões ativas."""
    status = {}

    for peer_id, connection in self.active_connections.items():
      status[peer_id] = {
        "ip": connection.peer_info.ip,
        "port": connection.peer_info.port,
        "name": connection.peer_info.name,
        "namespace": connection.peer_info.namespace,
        "is_connected": connection.is_connected(),
        "last_active": connection.last_active_timestamp,
      }
    return status

  def get_avg_rtts(self) -> Dict[str, float]:
    """Retorna o RTT médio para cada peer conectado."""
    rtt_data = {}

    for peer_id, connection in self.active_connections.items():
      rtt_data[peer_id] = connection.get_average_rtt()
    return rtt_data

  def reconnect_peers(self):
    """Força a reconciliação imediata das conexões de peers."""
    asyncio.run_coroutine_threadsafe(self._reconcile_connections(), self.get_event_loop())

  def set_log_level(self, level: str):
    """Define o nível de log para o cliente P2P."""
    numeric_level = getattr(logging, level.upper(), None)
    if not isinstance(numeric_level, int):
      raise ValueError(f'Invalid log level: {level}')
    logging.getLogger().setLevel(numeric_level)

def set_local_identity(name: str, namespace: str, port: int):
  """Define a identidade local do peer."""
  global LOCAL_STATE
  LOCAL_STATE.name = name
  LOCAL_STATE.namespace = namespace
  LOCAL_STATE.listen_port = port
  LOCAL_STATE.peer_id = f"{name}@{namespace}"
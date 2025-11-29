#gerenciamento de PING/PONG
# lógica principal
import asyncio
import time
import uuid
from typing import Optional, Dict, Any, TYPE_CHECKING


# Importações internas
import logging
from config import ProtocolConfig
from state import LOCAL_STATE
if TYPE_CHECKING:
  from peer_connection import PeerConnection

class KeepAliveManager:
  """Gerenciador principal da lógica de PING/PONG."""
  def __init__(self, active_connections: Dict[str, "PeerConnection"]):
    self.active_connections = active_connections
    self._periodic_tasks: Dict[str, asyncio.Task] = {} 
    self.pending_pings: Dict[str, tuple[str, float]] = {}
    self._is_running = False

  async def start(self):
    """Função assíncrona que gerencia o agendamento de tarefas."""
    logging.getLogger(__name__).info("[KeepAlive] start() chamado — iniciando tarefas periódicas.")

    self._is_running = True

    self._periodic_tasks['send_ping'] = asyncio.create_task(self._periodic_task_runner(self.send_ping, ProtocolConfig.PING_INTERVAL_SEC))
    self._periodic_tasks['check_timeout'] = asyncio.create_task(self._periodic_task_runner(self.check_timeout, ProtocolConfig.PONG_CHECK_INTERVAL_SEC))

    return

  async def _periodic_task_runner(self, func, interval: int):
    """Função utilitária para rodar uma função periodicamente."""
    while self._is_running:
      await func()
      await asyncio.sleep(interval)
  
  async def send_ping(self):
    """Envia um PING para todas as conexões ativas periodicamente."""
    logging.getLogger(__name__).debug("[KeepAlive] Executando send_ping().")

    connections = self.active_connections

    for peer_id, connection in connections.items():
      msg_id = str(uuid.uuid4())

      ts = time.time()
      self.pending_pings[peer_id] = (msg_id, time.time())

      message = {
        "type": "PING",
        "msg_id": msg_id,
        "src": LOCAL_STATE.peer_id,
        "timestamp": ts,
        "ttl": 1
      }

      await connection.send_message(message)
      logging.getLogger(__name__).debug(f"[KeepAlive] Registrando PING → peer={peer_id}, msg_id={msg_id}, ts={ts}")

  async def check_timeout(self):
    """Verifica se houve timeout de um dos pings a cada 10 segundos."""
    logging.getLogger(__name__).debug("[KeepAlive] Executando check_timeout().")

    connections = self.active_connections
    expired = []

    for peer_id, connection in connections.items():

      ping_info = self.pending_pings.get(peer_id)
      if ping_info and self.timeout(ping_info):
        expired.append(peer_id)
        logging.getLogger(__name__).warning(f"[KeepAlive] Timeout detectado para peer={peer_id}")

    # desconectar peers expirados (descomentar quando funções do peer_connection estiverem prontas)
    """
    for peer_id in expired:
      print(f"[KeepAlive] Timeout: {peer_id} não respondeu ao PING.")
      conn = self.active_connections.get(peer_id)
      if conn:
          await conn.close()
      self.pending_pings.pop(peer_id, None)
      self.active_connections.pop(peer_id, None)
    """

  def timeout(self, ping_info: tuple[str, float]):
    msg_id, ts = ping_info
    return time.time() - ts > ProtocolConfig.PONG_TIMEOUT_INTERVAL_SEC

  def handle_incoming_pong(self, message: Dict[str, Any]):
    """Realiza o tratamento de PONG."""
    peer_id = message.get("src")
    logging.getLogger(__name__).debug(f"[KeepAlive] PONG recebido de peer={peer_id}")

    if peer_id in self.pending_pings:
      stored_msg_id, sent_ts = self.pending_pings.pop(peer_id)
      rtt = time.time() - sent_ts
      logging.getLogger(__name__).debug(f"[KeepAlive] PONG recebido de {peer_id}. RTT: {rtt*1000:.2f} ms.")
    else:
      logging.getLogger(__name__).warning(f"[KeepAlive] PONG de {peer_id}, mas não havia ping pendente.")

  async def stop(self):
    """Para tudo no KeepAlive."""
    logging.getLogger(__name__).info("[KeepAlive] stop() chamado — cancelando tarefas.")

    self._is_running = False
    for t in self._periodic_tasks.values():
        t.cancel()
    await asyncio.gather(*self._periodic_tasks.values(), return_exceptions=True)
    self._periodic_tasks.clear()
  


    
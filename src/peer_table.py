import time
import random as rd
from typing import Dict, List, Optional

# Importa as estruturas de dados e configurações necessárias
from state import PEER_TABLE, PeerInfo, LOCAL_STATE
from config import ProtocolConfig

class PeerTableManager:
  """Gerencia a tabela de peers, incluindo adição, remoção e atualização, status(STALE) e reconexão (backoff exponencial)."""

  def __init__(self):
    """O manager opera sobre a PEER_TABLE global."""
    self._table = PEER_TABLE

  def update_from_discover(self, discovered_peers: List[dict]):
    """Processa a lista de peers recebidos do Rendezvous e atualiza a tabela de peers."""

    # Cria um conjunto de IDs descobertos para fácil verificação
    discovered_ids = {f"{p['name']}@{p['namespace']}" for p in discovered_peers}

    for peer_data in discovered_peers:
      peer_id = f"{peer_data['name']}@{peer_data['namespace']}"

      # Não se auto-adiciona
      if peer_id == LOCAL_STATE.peer_id:
        continue
      self._table.add_peer(peer_data)

      for id, peer in self._table.peers.items():
        # Marca peers não encontrados na descoberta como STALE
        if id not in discovered_ids:
          peer.is_stale = True
  
  def get_peer(self, peer_id: str) -> Optional[PeerInfo]:
    """Busca um peer na tabela pelo seu ID."""
    return self._table.peers.get(peer_id)
  
  def get_peers_to_connect(self) -> List[PeerInfo]:
    """Retorna uma lista de peers que precisam de uma conexão (não conectados e cujo tempo de reconexão expirou)."""
    now = time.time()

    peers_to_connect = []

    for peer_id, peer in self._table.peers.items():
      if (not peer.is_connected and # Não está conectado
          peer.reconnect_attempts < ProtocolConfig.MAX_RECONNECT_ATTEMPTS and # Não excedeu tentativas
          now >= peer.next_reconnect_time): # Tempo de reconexão expirou
        peers_to_connect.append(peer)

    return peers_to_connect

  def register_connection_failure(self, peer_id: str):
    """Registra uma falha de conexão para um peer, aplicando backoff exponencial."""
    peer = self.get_peer(peer_id)
    if not peer:
      return
    
    peer.reconnect_attempts += 1

    if peer.reconnect_attempts >= ProtocolConfig.MAX_RECONNECT_ATTEMPTS: # Marca como STALE se excedeu tentativas
      peer.is_stale = True
      print(f"[{peer_id}] Atingiu o máximo de tentativas de reconexão. Marcado como STALE.")
      peer.next_reconnect_time = float('inf') # Não tentar mais
      return

    # Calcula o tempo de backoff exponencial com jitter
    base_delay = ProtocolConfig.RECONNECT_BASE_DELAY_SEC
    delay = base_delay * (2 ** (peer.reconnect_attempts - 1))

    # Adiciona jitter aleatório
    jitter = rd.uniform(0, ProtocolConfig.RECONNECT_JITTER_SEC)
    delay += jitter

    peer.next_reconnect_time = time.time() + delay
    print(f"[{peer_id}] Falha de conexão registrada. Tentativa {peer.reconnect_attempts}. Próxima tentativa em {delay:.2f} segundos.")
  
  def register_successful_connection(self, peer_id: str):
    """Registra uma conexão bem-sucedida, resetando o estado de reconexão do peer."""
    peer = self.get_peer(peer_id)
    if not peer:
      return
    
    peer.is_connected = True
    peer.is_stale = False
    peer.reconnect_attempts = 0
    peer.next_reconnect_time = 0.0
    print(f"[{peer_id}] Conexão bem-sucedida. Estado de reconexão resetado.")

  def register_disconnection(self, peer_id: str):
    """Lidar com BYE/BYE_OK ou desconexões inesperadas."""
    peer = self.get_peer(peer_id)
    if not peer:
      return
    
    peer.is_connected = False
    print(f"[{peer_id}] Desconectado. Marcado como não conectado.")
    self.register_connection_failure(peer_id)

  def get_all_connected_peers(self) -> List[PeerInfo]:
    """Retorna uma lista de todos os peers atualmente conectados."""
    return [peer for peer in self._table.peers.values() if peer.is_connected]
  
  def get_peers_in_namespace(self, namespace: str) -> List[PeerInfo]:
    """Retorna uma lista de peers que pertencem a um namespace específico."""
    return [peer for peer in self._table.peers.values() if peer.namespace == namespace]
  
  def get_average_rtt(self, peer_id: str) -> Optional[float]:
    """Retorna o RTT médio para um peer específico, se disponível."""
    peer = self.get_peer(peer_id)
    if not peer or not peer.rtt_samples:
      return None
    return sum(peer.rtt_samples) / len(peer.rtt_samples)
  
PEER_MANAGER = PeerTableManager()
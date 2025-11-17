from dataclasses import dataclass, field
import time
from typing import Dict, Optional, Any

# --- Estruturas de Dados ---

@dataclass
class PeerInfo:
    """Representa as informações e o estado de um peer conhecido."""
    # Identificação do peer
    ip: str
    port: int
    name: str
    namespace: str
    peer_id: str = field(init=False)

    # Estado da conexão
    is_connected: bool = False
    is_stale: bool = False # Marcado se não respondeu ao último PING
    last_seen: float = field(default_factory=time.time) # Timestamp do último contato

    # Keep-Alive e Observabilidade
    last_ping_sent: Optional[float] = None
    last_pong_received: Optional[float] = None
    avg_rtt_ms: Optional[float] = None

    # Gerenciamento de Reconexões
    reconnect_attempts: int = 0
    next_reconnect_time: Optional[float] = None

    def __post_init__(self):
        """Define o peer_id após a inicialização."""
        self.peer_id = f"{self.name}@{self.namespace}"

@dataclass
class LocalPeerState:
    """Armazena a identidade e o estado do peer local."""
    name: str
    namespace: str
    listen_port: int

    # Informações observadas pelo Rendezvous (atualizadas no REGISTER)
    observed_ip: Optional[str] = None
    observed_port: Optional[int] = None

    peer_id: str = field(init=False)

    def __post_init__(self):
        """Define o peer_id após a inicialização."""
        self.peer_id = f"{self.name}@{self.namespace}"

@dataclass
class PeerTable:
    """Gerencia a coleção de todos os peers conhecidos pela rede."""

    # Dicionário de peers conhecidos, indexados por peer_id
    peers: Dict[str, PeerInfo] = field(default_factory=dict)

    def add_peer(self, peer_data: Dict[str, Any]):
        """Adiciona ou atualiza um peer na tabela."""
        
        # Cria um novo PeerInfo a partir dos dados fornecidos
        peer_info = PeerInfo(
            ip=peer_data['ip'],
            port=peer_data['port'],
            name=peer_data['name'],
            namespace=peer_data['namespace']
        )
        
        # Se o peer já existe, atualiza suas informações
        if peer_info.peer_id in self.peers:
            existing_peer = self.peers[peer_info.peer_id]
            existing_peer.ip = peer_info.ip
            existing_peer.port = peer_info.port
            existing_peer.last_seen = time.time()
        else:
            self.peers[peer_info.peer_id] = peer_info
            
# --- Inicialização do Estado Global ---

# Inicializa o estado do peer local com valores padrão que podem ser alterados na inicialização
LOCAL_STATE = LocalPeerState(
    name='aluno', # Nome padrão, pode ser alterado na inicialização
    namespace='UNB', # Namespace padrão, pode ser alterado na inicialização
    listen_port=7070 # Porta padrão, pode ser alterada na inicialização
)

# Inicializa a tabela de peers conhecidos (vazia no início)
PEER_TABLE = PeerTable()

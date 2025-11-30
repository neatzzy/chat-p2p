import json
import asyncio
import time
import uuid
from typing import Dict, Any, Optional, TYPE_CHECKING
import logging

from config import ProtocolConfig
from state import PeerInfo, LOCAL_STATE
from peer_table import PEER_MANAGER
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from message_router import MessageRouter

class PeerConnection:
    """Gerencia a conexão P2P com outro peer."""

    def __init__(self, peer_info: PeerInfo, reader: Optional[asyncio.StreamReader] = None, writer: Optional[asyncio.StreamWriter] = None):
        self.peer_info = peer_info
        self.reader = reader
        self.writer = writer
        self.is_active = False
        # O roteador será ligado pelo orquestrador (P2PClient) para evitar importações circulares
        self.router: "MessageRouter" | None = None
        # Rastreia timestamps e amostras de RTT para métricas simples
        self.last_active_timestamp: float | None = None
        self._rtt_samples: list[float] = []

  # Utilitários de codificação e envio de Mensagens

    def _encode_message(self, message: Dict[str, Any]) -> bytes:
        """Codifica a mensagem em bytes com o delimitador."""
        json_str = json.dumps(message)
        data = json_str.encode(ProtocolConfig.ENCODING) + ProtocolConfig.MESSAGE_DELIMITER

        if len(data) > ProtocolConfig.MAX_MESSAGE_SIZE_BYTES:
            raise ValueError("Mensagem excede o tamanho máximo permitido.")
        return data
    
    async def send_message(self, message: Dict[str, Any]):
        """Envia uma mensagem para o peer conectado."""
        logger = logging.getLogger(__name__)
        if not self.writer:
            logger.warning(f"[PeerConnection] Conexão não estabelecida com o peer {self.peer_info.peer_id}.")
            return
        
        try:
            data = self._encode_message(message)
            self.writer.write(data)
            await self.writer.drain()
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"[PeerConnection] [ERROR] Erro ao enviar mensagem para o peer {self.peer_info.peer_id}: {e}")
            await self.close()

    # Handshake (HELLO / HELLO_OK)

    async def _send_hello(self):
        """Envia a mensagem HELLO para o peer conectado."""
        hello_msg = {
            "type": "HELLO",
            "peer_id": LOCAL_STATE.peer_id,
            "version": "1.0",
            "features": ["ack", "metrics"],
            "ttl": ProtocolConfig.TTL
        }
        await self.send_message(hello_msg)

    async def do_handshake(self, is_initiator: bool, pre_received: Optional[Dict[str, Any]] = None) -> bool:
        """
        Realiza o Handshake HELLO/HELLO_OK, suportando fluxos Inbound e Outbound.
        
        Argumentos:
            is_initiator: True se somos o peer que iniciou a conexão TCP (Outbound), False se recebemos a conexão (Inbound).
        """
        try:
            if is_initiator:
                await self._send_hello()
                expeted_type = "HELLO_OK"
                flow_type = "OUTBOUND"
            else:
                expeted_type = "HELLO"
                flow_type = "INBOUND"

            logging.getLogger(__name__).debug(f"[PeerConnection] [Handshake] {flow_type} iniciado com {self.peer_info.peer_id}")

            # Se já recebemos a mensagem HELLO (fluxo Inbound), usamos ela
            if pre_received is None:
                data = await asyncio.wait_for(self.reader.readuntil(ProtocolConfig.MESSAGE_DELIMITER), timeout=ProtocolConfig.HANDSHAKE_TIMEOUT_SEC)
                message = self._decode_message(data)
            else:
                message = pre_received

            if message.get("type") != expeted_type:
                logging.getLogger(__name__).warning(f"[PeerConnection] [Handshake ERROR] Esperado {expeted_type}, recebido {message.get('type')}")
                return False
            
            remote_peer_id = message.get("peer_id")

            if not remote_peer_id:
                logging.getLogger(__name__).warning(f"[PeerConnection] [Handshake ERROR] peer_id ausente na mensagem")
                return False
            
            # Store remote peer_id for both initiator and responder flows
            self.peer_info.peer_id = remote_peer_id

            if not is_initiator:
                # For inbound connections, also update name/namespace from peer_id
                try:
                    name, namespace = remote_peer_id.split("@")
                    self.peer_info.name = name
                    self.peer_info.namespace = namespace
                except Exception:
                    pass

                hello_ok_msg = {
                    "type": "HELLO_OK",
                    "peer_id": LOCAL_STATE.peer_id,
                    "version": "1.0",
                    "features": ["ack", "metrics"],
                    "ttl": ProtocolConfig.TTL
                }
                await self.send_message(hello_ok_msg)

            self.is_active = True
            self.peer_info.is_connected = True
            logging.getLogger(__name__).info(f"[PeerConnection] [Handshake SUCCESS] Conexão {flow_type} estabelecida com {self.peer_info.peer_id}")
            return True
        
        except asyncio.TimeoutError:
            logging.getLogger(__name__).warning(f"[PeerConnection] [Handshake ERROR] Timeout durante o Handshake com {self.peer_info.peer_id}")
            return False
        except Exception as e:
            logging.getLogger(__name__).error(f"[PeerConnection] [Handshake ERROR] Erro inesperado durante o Handshake com {self.peer_info.peer_id}: {e}")
            return False

    # Ouvinte de conexão e loop principal

    async def run_listener(self):
        """Loop principal para ouvir mensagens do peer."""
        
        if not self.reader:
            logging.getLogger(__name__).warning(f"[PeerConnection] Listener iniciado sem StreamReader para o peer {self.peer_info.peer_id}.")
            return
        
        try:
            while self.is_active:
                data = await asyncio.wait_for(self.reader.readuntil(ProtocolConfig.MESSAGE_DELIMITER), timeout=ProtocolConfig.PING_INTERVAL_SEC * 2)

                message = self._decode_message(data)
                # Atualiza timestamp de atividade
                self.last_active_timestamp = time.time()

                # Encaminha a mensagem para o roteador de mensagens (se estiver ligado)
                if self.router:
                    await self.router.handle_incoming_message(self, message)
                else:
                    logging.getLogger(__name__).error(f"[PeerConnection] Sem router para processar mensagem de {self.peer_info.peer_id}: {message}")
                logging.getLogger(__name__).debug(f"[PeerConnection] Mensagem recebida do peer {self.peer_info.peer_id}: {message}")
        except asyncio.TimeoutError:
            logging.getLogger(__name__).warning(f"[PeerConnection] Timeout ao ler do peer {self.peer_info.peer_id}")
        except asyncio.IncompleteReadError:
            logging.getLogger(__name__).info(f"[PeerConnection] Conexão fechada pelo peer {self.peer_info.peer_id}")
        except Exception as e:
            logging.getLogger(__name__).error(f"[PeerConnection] [ERROR] Erro inesperado com {self.peer_info.peer_id}: {e}")
        finally:
            logging.getLogger(__name__).info(f"[PeerConnection] Encerrando conexão com o peer {self.peer_info.peer_id}")
            await self.close()

    def _decode_message(self, data: bytes) -> Dict[str, Any]:
        """Decodifica os bytes recebidos em uma mensagem JSON."""
        json_str = data.rstrip(ProtocolConfig.MESSAGE_DELIMITER).decode(ProtocolConfig.ENCODING)
        return json.loads(json_str)
    
    async def close(self):
        """Fecha a conexão com o peer."""
        self.is_active = False
        self.peer_info.is_connected = False
        self.peer_info.is_stale = True
        if self.writer:
            self.writer.close()
            await self.writer.wait_closed()

    async def send_bye_and_close(self):
        """Envia BYE para o peer e fecha a conexão."""
        try:
            msg_id = str(uuid.uuid4())
            message = {
                "type": "BYE",
                "msg_id": msg_id,
                "src": LOCAL_STATE.peer_id,
                "dst": self.peer_info.peer_id,
                "reason": "shutdown",
                "timestamp": time.time(),
                "ttl": 1,
            }
            await self.send_message(message)
        except Exception as e:
            logging.getLogger(__name__).error(f"[PeerConnection] [ERROR] Erro ao enviar BYE para {self.peer_info.peer_id}: {e}")
        finally:
            await self.close()

    def is_connected(self) -> bool:
        """Retorna se a conexão está ativa."""
        return self.is_active

    def add_rtt_sample(self, rtt: float) -> None:
        """Adiciona uma amostra RTT para cálculo médio."""
        self._rtt_samples.append(rtt)

    def get_average_rtt(self) -> float:
        """Retorna o RTT médio (ms) para este peer. 0.0 se não houver amostras."""
        if not self._rtt_samples:
            return 0.0
        return (sum(self._rtt_samples) / len(self._rtt_samples)) * 1000.0  # Converter para ms
    
    # Iniciar conexãoes OUTBOUND

async def create_outbound_connection(peer_info: PeerInfo) -> Optional['PeerConnection']:
        """Tenta estabelecer uma conexão TCP de saída com o peer e executa o Handshake."""
        try:
            # Aplique o timeout de conexão usando a configuração do protocolo
            conn_coro = asyncio.open_connection(peer_info.ip, peer_info.port)
            reader, writer = await asyncio.wait_for(conn_coro, timeout=ProtocolConfig.CONNECT_TIMEOUT_SEC)

            connection = PeerConnection(peer_info, reader, writer)

            if await connection.do_handshake(is_initiator=True):
                asyncio.create_task(connection.run_listener())
                return connection
            
            await connection.close()
            return None
        
        except Exception as e:
            logging.getLogger(__name__).warning(f"[PeerConnection] [ERROR] Falha ao conectar com o peer {peer_info.peer_id}: {e}")
            return None
            


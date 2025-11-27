import json
import asyncio
import time
from typing import Dict, Any, Optional, TYPE_CHECKING

from config import ProtocolConfig
from state import PeerInfo, LOCAL_STATE
from peer_table import PEER_MANAGER
if TYPE_CHECKING:
    from message_router import MessageRouter

class PeerConnection:
    """Gerencia a conexão P2P com outro peer."""

    def __init__(self, peer_info: PeerInfo, reader: Optional[asyncio.StreamReader] = None, writer: Optional[asyncio.StreamWriter] = None):
        self.peer_info = peer_info
        self.reader = reader
        self.writer = writer
        self.is_active = False
        self.router: MessageRouter = MessageRouter()

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
        if not self.writer:
            print(f"[PeerConnection] Conexão não estabelecida com o peer {self.peer_info.peer_id}.")
            return
        
        try:
            data = self._encode_message(message)
            self.writer.write(data)
            await self.writer.drain()
        except Exception as e:
            print(f"[PeerConnection] Erro ao enviar mensagem para o peer {self.peer_info.peer_id}: {e}")
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

    async def do_handshake(self, is_initiator: bool) -> bool:
        """
        Realiza o Handshake HELLO/HELLO_OK, suportando fluxos Inbound e Outbound.
        
        Args:
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

            print(f"[Handshake] {flow_type} iniciado com {self.peer_info.peer_id}")

            data = await asyncio.wait_for(self.reader.readuntil(ProtocolConfig.MESSAGE_DELIMITER), timeout=ProtocolConfig.HANDSHAKE_TIMEOUT_SEC)

            message = self._decode_message(data)

            if message.get("type") != expeted_type:
                print(f"[Handshake ERROR] Esperado {expeted_type}, recebido {message.get('type')}")
                return False
            
            remote_peer_id = message.get("peer_id")

            if not remote_peer_id:
                print(f"[Handshake ERROR] peer_id ausente na mensagem")
                return False
            
            if not is_initiator:
                name, namespace = remote_peer_id.split("@")
                self.peer_info.name = name
                self.peer_info.namespace = namespace
                self.peer_info.peer_id = remote_peer_id

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
            print(f"[Handshake SUCCESS] Conexão {flow_type} estabelecida com {self.peer_info.peer_id}")
            return True
        
        except asyncio.TimeoutError:
            print(f"[Handshake ERROR] Timeout durante o Handshake com {self.peer_info.peer_id}")
            return False
        except Exception as e:
            print(f"[Handshake ERROR] Erro inesperado durante o Handshake com {self.peer_info.peer_id}: {e}")
            return False

    # Ouvinte de conexão e loop principal

    async def run_listener(self):
        """Loop principal para ouvir mensagens do peer."""
        
        if not self.reader:
            print(f"[PeerConnection] Listener iniciado sem StreamReader para o peer {self.peer_info.peer_id}.")
            return
        
        try:
            while self.is_active:
                data = await asyncio.wait_for(self.reader.readuntil(ProtocolConfig.MESSAGE_DELIMITER), timeout=ProtocolConfig.PING_INTERVAL_SEC * 2)

                message = self._decode_message(data)

                # Encaminha a mensagem para o roteador de mensagens
                self.router.handle_incoming_message(self, message)
                print(f"[PeerConnection] Mensagem recebida do peer {self.peer_info.peer_id}: {message}")
        except asyncio.TimeoutError:
            print(f"[PeerConnection] Timeout ao ler do peer {self.peer_info.peer_id}")
        except asyncio.IncompleteReadError:
            print(f"[PeerConnection] Conexão fechada pelo peer {self.peer_info.peer_id}")
        except Exception as e:
            print(f"[PeerConnection] Erro inesperado com {self.peer_info.peer_id}: {e}")
        finally:
            print(f"[PeerConnection] Encerrando conexão com o peer {self.peer_info.peer_id}")
            await self.close()

    def _decode_message(self, data: bytes) -> Dict[str, Any]:
        """Decodifica os bytes recebidos em uma mensagem JSON."""
        json_str = data.rstrip(ProtocolConfig.MESSAGE_DELIMITER).decode(ProtocolConfig.ENCODING)
        return json.loads(json_str)
    
    async def close(self):
        """Fecha a conexão com o peer."""
        self.is_active = False
        if self.writer:
            self.writer.close()
            await self.writer.wait_closed()
    
    # Iniciar conexãoes OUTBOUND

async def create_outbound_connection(peer_info: PeerInfo) -> Optional['PeerConnection']:
        """Tenta estabelecer uma conexão TCP de saída com o peer e executa o Handshake."""
        try:
            reader, writer = await asyncio.open_connection(peer_info.ip, peer_info.port)

            connection = PeerConnection(peer_info, reader, writer)

            if await connection.do_handshake(is_initiator=True):
                asyncio.create_task(connection.run_listener())
                return connection
            
            await connection.close()
            return None
        
        except Exception as e:
            PEER_MANAGER.register_connection_failure(peer_info.peer_id)
            print(f"[PeerConnection] Falha ao conectar com o peer {peer_info.peer_id}: {e}")
            return None
            


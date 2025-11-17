import json
import asyncio
import time
from typing import Dict, Any, Optional

from config import ProtocolConfig
from state import PeerInfo, LOCAL_STATE
from peer_table import PEER_MANAGER
from message_router import MESSAGE_ROUTER

class PeerConnection:
    """Gerencia a conexão P2P com outro peer."""

    def __init__(self, peer_info: PeerInfo, reader: Optional[asyncio.StreamReader] = None, writer: Optional[asyncio.StreamWriter] = None):
        self.peer_info = peer_info
        self.reader = reader
        self.writer = writer
        self.is_active = False

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

    async def do_handshake(self):
        """Realiza o handshake inicial com o peer."""
        await self._send_hello()

        # Espera pela resposta HELLO_OK
        try:
            data = await asyncio.wait_for(self.reader.readuntil(ProtocolConfig.MESSAGE_DELIMITER), timeout=ProtocolConfig.HANDSHAKE_TIMEOUT_SEC)
            message = self._decode_message(data)

            if message.get("type") == "HELLO_OK":
                print(f"[PeerConnection] Handshake bem-sucedido com o peer {self.peer_info.peer_id}")
                self.peer_info.is_connected = True
                self.peer_info.last_seen = time.time()
                return True
            else:
                print(f"[PeerConnection] Resposta inesperada durante o handshake com {self.peer_info.peer_id}: {message}")
                return False
        except asyncio.TimeoutError:
            print(f"[PeerConnection] Timeout durante o handshake com o peer {self.peer_info.peer_id}")
            return False
        except Exception as e:
            print(f"[PeerConnection] Erro durante o handshake com o peer {self.peer_info.peer_id}: {e}")
            return False

    # Ouvinte de conexão e loop principal

    async def run_listener(self):
        """Loop principal para ouvir mensagens do peer."""
        
        if not self.reader:
            print(f"[PeerConnection] Listener iniciado sem StreamReader para o peer {self.peer_info.peer_id}.")
            return
        
        try:
            if not self.is_active:
                # Se for uma conexão INBOUND, realiza o handshake
                await self.do_handshake(is_initiator=False)
                self.is_active = True
            while self.is_active:
                data = await asyncio.wait_for(self.reader.readuntil(ProtocolConfig.MESSAGE_DELIMITER), timeout=ProtocolConfig.PING_INTERVAL_SEC * 2)

                message = self._decode_message(data)

                # Encaminha a mensagem para o roteador de mensagens
                MESSAGE_ROUTER.handle_incoming_message(self, message)
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

            if await connection.do_handshake():
                asyncio.create_task(connection.run_listener())
                return connection
            
            await connection.close()
            return None
        
        except Exception as e:
            PEER_MANAGER.register_connection_failure(peer_info.peer_id)
            print(f"[PeerConnection] Falha ao conectar com o peer {peer_info.peer_id}: {e}")
            return None
            


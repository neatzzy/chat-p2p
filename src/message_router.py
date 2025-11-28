#envio e publicação de mensagens

import asyncio
import time
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional, TYPE_CHECKING

import logging
from config import ProtocolConfig
from peer_table import PEER_MANAGER
from state import LOCAL_STATE

if TYPE_CHECKING:
    from peer_connection import PeerConnection
    from keep_alive import KeepAliveManager


# classe responsável pelo roteamento da mensagem

class MessageRouter:
    """
    Gerencia as conexões ativas e roteia mensagens entre os peers.
    """

    def __init__(self, connections: Optional[Dict[str, "PeerConnection"]] = None, keep_alive: Optional["KeepAliveManager"] = None):
        # Mapeia peer_id(str) para sua conexão ativa (PeerConnection)
        self.connections: Dict[str, "PeerConnection"] = connections if connections is not None else {}
        # Rastreamento de estado de protocolo(acks)
        self.keep_alive: Optional["KeepAliveManager"] = keep_alive
        self.pending_acks: Dict[str, asyncio.Task] = {}
        
    def register_connection(self, peer_id: str, connection: PeerConnection):
        # Registra conexão P2P bem sucedida
        self.connections[peer_id] = connection
        PEER_MANAGER.register_successful_connection(peer_id)

    def unregister_connection(self, peer_id: str):
        # Remove conexão
        connection = self.connections.pop(peer_id, None)
        if connection is None:
            return
        # Limpa ACKs pendentes 
        acks_to_remove = [msg_id for msg_id, task in self.pending_acks.items() if task.get_name().startswith(peer_id)]
        for msg_id in acks_to_remove:
            self.pending_acks[msg_id].cancel()
            del self.pending_acks[msg_id]
            logging.getLogger(__name__).debug(f"[Router] ACK pendente {msg_id} para {peer_id} cancelado.")
        # Informa PEER_MANAGER
        PEER_MANAGER.register_disconnection(peer_id)

    async def handle_incoming_message(self, connection: PeerConnection, message: Dict[str, Any]):

        # Processas uma mensagem recebida de um PeerConnection
        msg_type = message.get("type")
        peer_id = message.get("src")
        msg_id = message.get("msg_id")

        # TTL enforcement: drop messages with ttl <= 0
        try:
            ttl = int(message.get("ttl", 1))
        except Exception:
            ttl = 1
        if ttl <= 0:
            logging.getLogger(__name__).debug(f"[MessageRouter] Dropping message with ttl<=0 from {peer_id}: {msg_type} ({msg_id})")
            return
        # decrement ttl for forwarding (if applicable)
        message["ttl"] = ttl - 1

        if peer_id:
        # Atualiza visto por último
            peer = PEER_MANAGER.get_peer(peer_id)
            if peer:
                peer.last_seen = time.time()

        if msg_type == "SEND":
        # Mensagem direta
            payload = message.get("payload", "")
            # Mensagem para usuário: mostrar em stdout
            print(f"\n[Mensagem de {peer_id}]: {payload}\n> ", end="")
            if message.get("require_ack"):
                # reply ACK to sender using same msg_id as reference
                logging.getLogger(__name__).debug(f"[MessageRouter] Enviando ACK para {peer_id} (ref: {msg_id}).")
                await self.send_ack(connection, msg_id, peer_id)

        elif msg_type == "ACK":
        # Confirmação de recebimento
            logging.getLogger(__name__).debug(f"[MessageRouter] ACK recebido de {peer_id} (ref: {msg_id}).")
            if msg_id in self.pending_acks:
                task = self.pending_acks[msg_id]
                # cancel the timeout task and remove pending ack
                try:
                    task.cancel()
                except Exception:
                    pass
                del self.pending_acks[msg_id]
            else:
                logging.getLogger(__name__).warning(f"[MessageRouter] ACK inesperado recebido de {peer_id} (ref: {msg_id}).")

        elif msg_type == "PUB":
        # Mensagem de difusão
            dst = message.get("dst", "*")
            payload = message.get("payload", "")
            # Broadcast shown to user
            print(f"\n[Broadcast {dst} de {peer_id}]: {payload}\n> ", end="")

        elif msg_type == "PING":
        # Keep-alive(ida)
            logging.getLogger(__name__).debug(f"[MessageRouter] PING recebido de {peer_id} (msg_id: {msg_id}).")
            await self.send_pong(connection, msg_id, peer_id)

        elif msg_type == "PONG":
        # Keep-alive(volta)
            # Atualiza keep-alive e métricas locais
            if self.keep_alive:
                self.keep_alive.handle_incoming_pong(message)
            else:
                logging.getLogger(__name__).warning("[MessageRouter] PONG recebido mas KeepAliveManager não está ligado.")

            # Se possível, atualiza RTT na conexão a partir do timestamp enviado no PONG
            try:
                sent_ts = message.get("timestamp")
                if sent_ts is not None:
                    rtt = time.time() - float(sent_ts)
                    if connection and hasattr(connection, 'add_rtt_sample'):
                        connection.add_rtt_sample(rtt)
            except Exception:
                pass

        elif msg_type == "BYE":
        # Fim de sessão(ida)
            reason = message.get("reason", "N/A")
            logging.getLogger(__name__).info(f"[MessageRouter] {peer_id} enviou BYE (Razão: {reason}). Respondendo BYE_OK.")
            await self.send_bye_ok(connection, msg_id, peer_id)
            await connection.close()
        elif msg_type == "BYE_OK":
        # Fim de sessão(volta)
            logging.getLogger(__name__).info(f"[MessageRouter] {peer_id} respondeu BYE_OK. Fechando conexão.")
            await connection.close()
        else:
            logging.getLogger(__name__).warning(f"[MessageRouter] Tipo de mensagem desconhecido de {peer_id}: {msg_type}")

    def get_timestamp(self) -> str:
        # Retorna timestamp UTC ISO 8601.
        return datetime.now(timezone.utc).isoformat()

    async def handle_ack_timeout(self, msg_id: str, peer_id: str):
        # Mensagens sem ACK após ACK_TIMEOUT_SEC geram aviso de timeout no log.
        try:
            await asyncio.sleep(ProtocolConfig.ACK_TIMEOUT_SEC)
            if msg_id in self.pending_acks:
                # timeout reached
                del self.pending_acks[msg_id]
                logging.getLogger(__name__).warning(f"[Timeout] A mensagem {msg_id} para {peer_id} expirou (sem ACK).")
                # Optionally record a connection failure or metric
                try:
                    PEER_MANAGER.register_connection_failure(peer_id)
                except Exception:
                    pass
        except asyncio.CancelledError:
            # normal cancellation when ACK arrives
            pass

    async def send_unicast(self, target_peer_id: str, payload: str, require_ack: bool = False):
        # Envia mensagem direta
        if target_peer_id not in self.connections:
            logging.getLogger(__name__).warning(f"[Erro] Sem conexão ativa com {target_peer_id}.")
            return
    
        connection = self.connections[target_peer_id]
        msg_id = str(uuid.uuid4())

        message = {
            "type": "SEND",
            "msg_id": msg_id,
            "src": LOCAL_STATE.peer_id,
            "dst": target_peer_id,
            "payload": payload,
            "require_ack": require_ack,
            "timestamp": self.get_timestamp(),
            "ttl": 1
        }
        # Envia realmente a mensagem (respeitando ttl)
        await connection.send_message(message)
        if require_ack:
            # cria task para timeout de ACK e nomeia com peer:msg para facilitar debug
            t = asyncio.create_task(self.handle_ack_timeout(msg_id, target_peer_id))
            try:
                t.set_name(f"ack_timeout:{target_peer_id}:{msg_id}")
            except Exception:
                pass
            self.pending_acks[msg_id] = t

    async def send_ack(self, connection: "PeerConnection", msg_id: str, target_peer_id: str):
        message = {
            "type": "ACK",
            "msg_id": msg_id,
            "src": LOCAL_STATE.peer_id,
            "dst": target_peer_id,
            "timestamp": self.get_timestamp(),
            "ttl": 1
        }
        await connection.send_message(message)

    async def send_bye_ok(self, connection: "PeerConnection", msg_id: str, target_peer_id: str):
        message = {
            "type": "BYE_OK",
            "msg_id": msg_id,
            "src": LOCAL_STATE.peer_id,
            "dst": target_peer_id,
            "timestamp": self.get_timestamp(),
            "ttl": 1
        }
        await connection.send_message(message)

    async def send_pong(self, connection: PeerConnection, msg_id: str, target_peer_id: str):
        # Envia PONG
        message = {
            "type": "PONG",
            "msg_id": msg_id, 
            "src": LOCAL_STATE.peer_id,
            "dst": target_peer_id,
            "timestamp": self.get_timestamp(),
            "ttl": 1
        }
        await connection.send_message(message)

    async def handle_outbound_pub(self, pub_message: Dict[str, Any], active_connections: Dict[str, "PeerConnection"]):
        """Publica uma mensagem para peers ativos que correspondam ao namespace ou para todos se dst=='*'."""
        dst = pub_message.get('dst', '*')
        sent = 0
        for peer_id, conn in active_connections.items():
            try:
                if dst == '*' or dst == conn.peer_info.namespace:
                    await conn.send_message(pub_message)
                    sent += 1
            except Exception as e:
                logging.getLogger(__name__).warning(f"[MessageRouter] Falha ao enviar PUB para {peer_id}: {e}")
        logging.getLogger(__name__).info(f"[MessageRouter] PUB enviado para {sent} peers (dst={dst}).")


# Instância global do roteador, pode ser reassociada/wired pelo orquestrador
MESSAGE_ROUTER = MessageRouter()
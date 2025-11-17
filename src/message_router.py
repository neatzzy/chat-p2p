#envio e publicação de mensagens

import asyncio
import time
from typing import Dict, Any, Optional

from peer_connection import PeerConnection
from peer_table import PEER_MANAGER
from state import LOCAL_STATE


# classe responsável pelo roteamento da mensagem

class MessageRouter:
    """
    Gerencia as conexões ativas e roteia mensagens entre os peers.
    """

    def __init__(self):
        # Mapeia peer_id(str) para sua conexão ativa (PeerConnection)
        self.connections: Dict[str, PeerConnection] = {}
        # Rastreamento de estado de protocolo(pings e acks)
        self.pending_pings: Dict[str, float] = {}
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
            print(f"[Router] ACK pendente {msg_id} para {peer_id} cancelado.")
        # Informa PEER_MANAGER
        PEER_MANAGER.register_disconnection(peer_id)

    async def handle_incoming_message(self, connection: PeerConnection, message: Dict[str, Any]):

        # Processas uma mensagem recebida de um PeerConnection
        msg_type = message.get("type")
        peer_id = message.get("src")
        msg_id = message.get("msg_id")

        if peer_id:
        # Atualiza visto por último
            peer = PEER_MANAGER.get_peer(peer_id)
            if peer:
                peer.last_seen = time.time()

        if msg_type == "SEND":
        # Mensagem direta
            payload = message.get("payload", "")
            print(f"\n[Mensagem de {peer_id}]: {payload}\n> ", end="")
            if message.get("require_ack"):
                print(f"[MessageRouter] Enviando ACK para {peer_id} (ref: {msg_id}).")
                await self.send_ack(connection, msg_id, peer_id)

        elif msg_type == "ACK":
        # Confirmação de recebimento
            print(f"[MessageRouter] ACK recebido de {peer_id} (ref: {msg_id}).")
            if msg_id in self.pending_acks:
                self.pending_acks[msg_id].cancel()
                del self.pending_acks[msg_id]
            else:
                print(f"[MessageRouter] ACK inesperado recebido de {peer_id} (ref: {msg_id}).")

        elif msg_type == "PUB":
        # Mensagem de difusão
            dst = message.get("dst", "*")
            payload = message.get("payload", "")
            print(f"\n[Broadcast {dst} de {peer_id}]: {payload}\n> ", end="")

        elif msg_type == "PING":
        # Keep-alive(ida)
            print(f"[MessageRouter] PING recebido de {peer_id} (msg_id: {msg_id}).")
            await self.send_pong(connection, msg_id, peer_id)

        elif msg_type == "PONG":
        # Keep-alive(volta)
            if msg_id in self.pending_pings:
                start_time = self.pending_pings.pop(msg_id)
                rtt = time.time() - start_time
                print(f"[MessageRouter] LOG: PONG recebido de {peer_id}. RTT: {rtt*1000:.2f} ms.")
            else:
                print(f"[MessageRouter] PONG inesperado de {peer_id}.")

        elif msg_type == "BYE":
        # Fim de sessão(ida)
            reason = message.get("reason", "N/A")
            print(f"[MessageRouter] {peer_id} enviou BYE (Razão: {reason}). Respondendo BYE_OK.")
            await self.send_bye_ok(connection, msg_id, peer_id)
            await connection.close()
        elif msg_type == "BYE_OK":
        # Fim de sessão(volta)
            print(f"[MessageRouter] {peer_id} respondeu BYE_OK. Fechando conexão.")
            await connection.close()
        else:
            print(f"[MessageRouter] Tipo de mensagem desconhecido de {peer_id}: {msg_type}")

# Instância
MESSAGE_ROUTER = MessageRouter()
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
        # pending_acks mantém Task do watchdog por msg_id
        self.pending_acks: Dict[str, asyncio.Task] = {}
        # _ack_waiters permite sinalizar a chegada do ACK para um msg_id (Event)
        self._ack_waiters: Dict[str, asyncio.Event] = {}
        
    def register_connection(self, peer_id: str, connection: "PeerConnection"):
        # Registra conexão P2P bem sucedida
        self.connections[peer_id] = connection
        PEER_MANAGER.register_successful_connection(peer_id)

    def unregister_connection(self, peer_id: str):
        # Remove conexão
        connection = self.connections.pop(peer_id, None)
        if connection is None:
            return
        # Limpa ACKs pendentes 
        acks_to_remove = [msg_id for msg_id, task in self.pending_acks.items() if peer_id in (task.get_name() or '')]
        for msg_id in acks_to_remove:
            try:
                self.pending_acks[msg_id].cancel()
            except Exception:
                pass
            self.pending_acks.pop(msg_id, None)
            # também remove waiter se existir
            self._ack_waiters.pop(msg_id, None)
            logging.getLogger(__name__).debug(f"[Router] ACK pendente {msg_id} para {peer_id} cancelado.")
        # Informa PEER_MANAGER
        PEER_MANAGER.register_disconnection(peer_id)

    async def handle_incoming_message(self, connection: "PeerConnection", message: Dict[str, Any]):

        # Processas uma mensagem recebida de um PeerConnection
        msg_type = message.get("type")
        peer_id = message.get("src")
        # Se a mensagem recebida não contiver `src` (alguns peers podem omitir),
        # tenta-se obter o ID a partir de `connection.peer_info` quando possível e
        # garante-se que `message['src']` esteja presente para que componentes
        # posteriores (ex.: KeepAlive) possam utilizá-lo.
        if not peer_id and connection is not None and hasattr(connection, 'peer_info'):
            try:
                inferred = getattr(connection.peer_info, 'peer_id', None)
                if inferred:
                    peer_id = inferred
                    message.setdefault('src', peer_id)
            except Exception:
                pass
        msg_id = message.get("msg_id")

        # Aplicação de TTL: descarta mensagens com ttl <= 0
        try:
            ttl = int(message.get("ttl", 1))
        except Exception:
            ttl = 1
        if ttl <= 0:
            logging.getLogger(__name__).debug(f"[MessageRouter] Mensagem descartada por ttl<=0 de {peer_id}: {msg_type} ({msg_id})")
            return
        # decrementa o ttl para reencaminhamento (se aplicável)
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
                # responde com ACK ao remetente usando o mesmo msg_id como referência
                logging.getLogger(__name__).debug(f"[MessageRouter] Enviando ACK para {peer_id} (ref: {msg_id}).")
                await self.send_ack(connection, msg_id, peer_id)

        elif msg_type == "ACK":
        # Confirmação de recebimento
            logging.getLogger(__name__).debug(f"[MessageRouter] ACK recebido de {peer_id} (ref: {msg_id}).")
            # Se existe um waiter, sinaliza-o para que o watchdog finalize corretamente
            waiter = self._ack_waiters.get(msg_id)
            if waiter:
                try:
                    waiter.set()
                except Exception:
                    pass

            if msg_id in self.pending_acks:
                # O watchdog fará a limpeza quando detectar o waiter setado; apenas logamos aqui
                logging.getLogger(__name__).debug(f"[MessageRouter] ACK correspondendo a watchdog para {peer_id} (ref: {msg_id}).")
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
            self.unregister_connection(peer_id)
        elif msg_type == "BYE_OK":
        # Fim de sessão(volta)
            logging.getLogger(__name__).info(f"[MessageRouter] {peer_id} respondeu BYE_OK. Fechando conexão.")
            await connection.close()
        else:
            logging.getLogger(__name__).warning(f"[MessageRouter] Tipo de mensagem desconhecido de {peer_id}: {msg_type}")

    def get_timestamp(self) -> str:
        # Retorna timestamp em segundos epoch (float) para facilitar cálculo de RTT
        return time.time()

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

    async def _ack_watchdog(self, msg_id: str, peer_id: str, connection: "PeerConnection", message: Dict[str, Any], max_retries: int = 3):
        """Monitora a chegada do ACK e reenvia a mensagem em caso de timeout.

        Estratégia:
        - espera por `ProtocolConfig.ACK_TIMEOUT_SEC` por vez (exponencial),
        - se o waiter não for acionado, reenvia a vez e aumenta o delay,
        - ao receber ACK (outro código chama `waiter.set()`), o watchdog termina e limpa estruturas.
        """
        delay = ProtocolConfig.ACK_TIMEOUT_SEC
        retries = 0
        waiter = asyncio.Event()
        self._ack_waiters[msg_id] = waiter

        try:
            while retries < max_retries:
                try:
                    await asyncio.wait_for(waiter.wait(), timeout=delay)
                    # ACK recebido
                    logging.getLogger(__name__).debug(f"[ACK Watchdog] ACK recebido para {msg_id} (peer={peer_id}).")
                    break
                except asyncio.TimeoutError:
                    # retransmit
                    retries += 1
                    try:
                        logging.getLogger(__name__).warning(f"[ACK Watchdog] Reenvio {retries}/{max_retries} de {msg_id} para {peer_id}.")
                        await connection.send_message(message)
                    except Exception as e:
                        logging.getLogger(__name__).error(f"[ACK Watchdog] Falha ao reenviar {msg_id} para {peer_id}: {e}")
                    delay *= 2

            # Se saiu do loop sem que waiter fosse setado -> falha final
            if not waiter.is_set():
                logging.getLogger(__name__).warning(f"[ACK Watchdog] Sem ACK após {retries} tentativas para {msg_id} -> registrando falha de conexão {peer_id}.")
                try:
                    PEER_MANAGER.register_connection_failure(peer_id)
                except Exception:
                    pass

        except asyncio.CancelledError:
            # Cancelamento externo (por ex. desconexão) — apenas limpa
            logging.getLogger(__name__).debug(f"[ACK Watchdog] Cancelado para {msg_id} (peer={peer_id}).")
        finally:
            # cleanup: remover entradas pendentes
            try:
                self.pending_acks.pop(msg_id, None)
            except Exception:
                pass
            try:
                self._ack_waiters.pop(msg_id, None)
            except Exception:
                pass

    async def send_unicast(self, target_peer_id: str, payload: str, require_ack: bool = True):
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
            # cria task watchdog para gerenciar retransmissões de ACK e nomeia para debug
            t = asyncio.create_task(self._ack_watchdog(msg_id, target_peer_id, connection, message, max_retries=3))
            try:
                t.set_name(f"ack_watchdog:{target_peer_id}:{msg_id}")
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

    async def send_pong(self, connection: "PeerConnection", msg_id: str, target_peer_id: str):
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
import json
import asyncio

from config import RendezvousConfig, ProtocolConfig
from state import LOCAL_STATE
from typing import Dict, Any, Optional, List

class RendezvousConnectionError(Exception):
    """Exceção personalizada para erros de conexão com o Rendezvous."""
    pass

class RendezvousConnection:
    """Gerencia a conexão com o servidor Rendezvous para registro e descoberta de peers."""

    def __init__(self):
        self.host = RendezvousConfig.HOST
        self.port = RendezvousConfig.PORT

    async def _send_and_receive(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Função utilitária para enviar uma mensagem e receber a resposta do servidor Rendezvous."""
        try:
            # Estabelece a conexão TCP
            reader, writer = await asyncio.open_connection(self.host, self.port)

            # Codifica a mensagem como JSON e envia
            json_message = json.dumps(message)
            data_to_send = json_message.encode(ProtocolConfig.ENCODING) + ProtocolConfig.MESSAGE_DELIMITER

            # Checa o tamanho da mensagem
            if len(data_to_send) > ProtocolConfig.MAX_MESSAGE_SIZE_BYTES:
                raise RendezvousConnectionError("Mensagem excede o tamanho máximo permitido.")
            
            writer.write(data_to_send)
            await writer.drain()

            # Recebe a resposta
            response_data = await reader.readuntil(ProtocolConfig.MESSAGE_DELIMITER)

            # Fechar e Decodificar
            writer.close()
            await writer.wait_closed()

            response_json = response_data.rstrip(ProtocolConfig.MESSAGE_DELIMITER).decode(ProtocolConfig.ENCODING)
            response = json.loads(response_json)

            # Checar status da resposta
            if response.get("status") != "OK":
                raise RendezvousConnectionError(f"Erro do servidor Rendezvous: {response.get('error', 'Desconhecido')}")
            
            return response
        
        except (ConnectionRefusedError, TimeoutError, asyncio.IncompleteReadError, ConnectionError) as e:
            raise RendezvousConnectionError(f"Erro de conexão com o Rendezvous: {str(e)}")
        except json.JSONDecodeError as e:
            raise RendezvousConnectionError(f"Resposta inválida do servidor Rendezvous: {str(e)}")

    async def register(self) -> bool:
        """Registra o peer local no servidor Rendezvous.
        Atualiza o estado local com 'observed_ip' e 'observed_port'."""
        message = {
            "type": "REGISTER",
            "namespace": LOCAL_STATE.namespace,
            "name": LOCAL_STATE.name,
            "port": LOCAL_STATE.listen_port,
            "ttl": RendezvousConfig.REGISTER_REFRESH_INTERVAL_SEC
        }

        try:
            response = await self._send_and_receive(message)
            LOCAL_STATE.observed_ip = response.get("observed_ip")
            LOCAL_STATE.observed_port = response.get("observed_port")
            
            print(f"[Rendezvous] Registro OK. IP Observado: {LOCAL_STATE.observed_ip}:{LOCAL_STATE.observed_port}")
            return True
        except RendezvousConnectionError as e:
            print(f"[Rendezvous ERROR] Falha no registro: {str(e)}")
            return False
        
    async def discover(self, namespace: Optional[str] = None) -> List[Dict[str, Any]]:
        """Descobre peers registrados no servidor Rendezvous."""
        message = { "type": "DISCOVER" }

        if namespace: 
            message["namespace"] = namespace

        try:
            response = await self._send_and_receive(message)
            peers = response.get("peers", [])

            print(f"[Rendezvous] Descobertos {len(peers)} peers.")

            return response.get("peers", [])
        except RendezvousConnectionError as e:
            print(f"[Rendezvous ERROR] Falha ao descobrir peers: {str(e)}")
            return []
        
    async def unregister(self) -> bool:
        """Remove o registro do peer local do servidor Rendezvous."""

        message = {
            "type": "UNREGISTER",
            "namespace": LOCAL_STATE.namespace,
            "name": LOCAL_STATE.name,
            "port": LOCAL_STATE.listen_port
        }

        try:
            await self._send_and_receive(message)
            print(f"[Rendezvous] Unregister OK.")
            return True
        except RendezvousConnectionError as e:
            print(f"[Rendezvous ERROR] Falha ao desregistrar: {str(e)}")
            return False
        
# Instance global para uso na aplicação
RENDEZVOUS_CONNECTION = RendezvousConnection()
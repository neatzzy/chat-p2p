import os
from pathlib import Path
from dotenv import load_dotenv

# --- Configurações de Ambiente ---
BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / '.env'
LOG_FILE = BASE_DIR / 'p2p_client.log'
load_dotenv(dotenv_path=ENV_PATH)

# --- Carrega variáveis de ambiente ---
RZV_HOST = os.getenv('IP', 'localhost')
RZV_PORT = int(os.getenv('PORT', 8080))
RZV_LISTEN_PORT = int(os.getenv('LISTEN_PORT', 7070))

# --- Configurações do Servidor Rendezvous ---

class RendezvousConfig:
    """Configurações de conexão com o Servidor Rendezvous."""
    
    # Endereço e porta do servidor público
    HOST = RZV_HOST
    PORT = RZV_PORT
    
    # Intervalo (em segundos) para refresh do REGISTER e DISCOVER contínuo
    REGISTER_REFRESH_INTERVAL_SEC = 7200 # 2 horas
    DISCOVER_INTERVAL_SEC = 10 # Descoberta de peer's a cada 10 segundos


# --- Configurações do Protocolo P2P ---

class ProtocolConfig:
    """Parâmetros do protocolo P2P entre peers."""

    # Transporte e Codificação
    ENCODING = 'utf-8'
    MESSAGE_DELIMITER = b'\n' # O delimitador é importante para leitura de stream TCP
    MAX_MESSAGE_SIZE_BYTES = 32768 # 32 KiB (conforme especificação)

    # Time-to-Live (TTL) fixo
    TTL = 1 # Fixo em 1

    # Keep-Alive (PING/PONG)
    PING_INTERVAL_SEC = 30 # Envio de PING a cada 30 segundos 
    PONG_TIMEOUT_INTERVAL_SEC = 15 # Timeout de PONG após 15 segundos
    PONG_CHECK_INTERVAL_SEC = 10 # Checa se um PONG chegou a cada 10 segundos
    
    # Timeout para ACK
    ACK_TIMEOUT_SEC = 5 # Mensagens sem ACK após 5s geram aviso de timeout

    # Gerenciamento de Conexões e Reconexões
    MAX_RECONNECT_ATTEMPTS = 5 # Número máximo de tentativas de reconexão
    
    # Configuração de Backoff Exponencial (base e fator de jitter)
    RECONNECT_BASE_DELAY_SEC = 2
    RECONNECT_JITTER_FACTOR = 0.5

    # Timeout de conexão TCP
    HANDSHAKE_TIMEOUT_SEC = 5 # Timeout para completar o handshake HELLO/HELLO_OK
    # Timeout ao estabelecer a conexão TCP (connect)
    CONNECT_TIMEOUT_SEC = 5


# --- Configurações da Interface de Usuário (CLI) ---

class CLIConfig:
    """Configurações para a interface de linha de comando."""
    
    # Prompt da CLI
    PROMPT = "> "
    
    # Nível de log padrão
    DEFAULT_LOG_LEVEL = "INFO" # DEBUG, INFO, WARNING, ERROR, CRITICAL
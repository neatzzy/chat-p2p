[![CI](https://github.com/neatzzy/chat-p2p/actions/workflows/ci.yml/badge.svg)](https://github.com/neatzzy/chat-p2p/actions/workflows/ci.yml)

# 🐍 PyP2p: Cliente de Chat Peer-to-Peer

## 📖 Visão Geral do Projeto

O **PyP2p** é a implementação de um cliente de chat baseado na **arquitetura Peer-to-Peer (P2P) de conexão direta**.

O objetivo principal é exercitar conceitos de redes e protocolos de aplicação, permitindo que os usuários troquem mensagens diretas (**SEND**) e de difusão (**PUB**) em tempo real. O sistema não utiliza _relays_ ou múltiplos saltos; a comunicação é estabelecida diretamente entre peers acessíveis.

### 🔑 Características Principais

-  **Descoberta Centralizada:** Utiliza um **Servidor Rendezvous** para registro e descoberta inicial de peers.
-  **Conexões Persistentes:** Mantém conexões TCP de longa duração entre peers.
-  **Protocolo de Aplicação Próprio:** Implementa um protocolo de comunicação para _Handshake_ (`HELLO`/`HELLO_OK`), _Keep-Alive_ (`PING`/`PONG`) e troca de mensagens.
-  **Escopos de Mensagem:** Suporte a **Unicast** (`peer_id`), **Namespace-cast** (`#namespace`) e **Broadcast Global** (`*`).
-  **Gerenciamento Dinâmico:** Lida com a entrada e saída de peers da rede (_churn_) através de descoberta contínua e lógica de reconexão.

---

## 📡 Funcionamento Básico da Rede

O cliente opera em duas frentes de comunicação distintas:

### 1. Comunicação com o Servidor Rendezvous

O Rendezvous atua como um "ponto de encontro" centralizado para a descoberta de pares:

| Comando          | Função                                                                          |
| :--------------- | :------------------------------------------------------------------------------ |
| **`REGISTER`**   | O cliente anuncia sua identidade (`name@namespace`), IP e porta para a rede.    |
| **`DISCOVER`**   | O cliente requisita a lista de todos os peers ativos (global ou por namespace). |
| **`UNREGISTER`** | Encerra a sessão, removendo o cliente da lista ativa.                           |

A comunicação com o Rendezvous é periódica e automática, garantindo que o peer permaneça visível e atualize sua lista de peers ativos.

### 2. Protocolo de Comunicação entre Peers (P2P)

Após descobrir um peer, o cliente estabelece uma conexão TCP persistente e utiliza os seguintes comandos para a sessão:

| Comando                | Descrição                                                                                                                 |
| :--------------------- | :------------------------------------------------------------------------------------------------------------------------ |
| **`HELLO`/`HELLO_OK`** | Handshake inicial para estabelecer a conexão e trocar informações de identidade.                                          |
| **`PING`/`PONG`**      | Mensagens de _Keep-Alive_ trocadas a cada 30 segundos para manter a conexão ativa e calcular o **RTT** (Round Trip Time). |
| **`SEND`/`ACK`**       | Envio de mensagens diretas (Unicast). Opcionalmente requer uma confirmação (`ACK`).                                       |
| **`PUB`**              | Mensagens de difusão (Namespace-cast ou Broadcast Global).                                                                |
| **`BYE`/`BYE_OK`**     | Encerramento limpo e controlado da sessão.                                                                                |

---

## 🏗️ Arquitetura de Módulos (Divisão de Responsabilidades)

O projeto segue um modelo de arquitetura modular, onde cada arquivo Python tem uma responsabilidade única e clara, facilitando a manutenção e o desenvolvimento concorrente.

| Módulo                         | Responsabilidade                                                                                                                                                                           |
| :----------------------------- | :----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **`main.py`**                  | Ponto de entrada. Inicialização do sistema de _logging_ e do orquestrador principal (`p2p_client.py`).                                                                                     |
| **`config.py`**                | **Configuração.** Armazena constantes do sistema (endereço do Rendezvous, intervalos, limites).                                                                                            |
| **`state.py`**                 | **Dados Compartilhados.** Armazena a identidade do peer local e a estrutura de dados da **`PeerTable`** (lista de peers conhecidos).                                                       |
| **`rendezvous_connection.py`** | **Interface Rendezvous.** Lógica para construir e enviar mensagens `REGISTER`, `DISCOVER`, `UNREGISTER` e processar suas respostas.                                                        |
| **`peer_table.py`**            | **Gerenciamento de Peers.** Lógica para atualizar a lista de peers, marcar como `STALE` e aplicar a política de **backoff exponencial** para reconexão.                                    |
| **`peer_connection.py`**       | **Camada TCP.** Gerencia uma única conexão TCP, manipulação de JSON (codificação/decodificação) e o _Handshake_ (`HELLO`/`HELLO_OK`).                                                      |
| **`keep_alive.py`**            | **Keep-Alive.** Agendamento periódico de `PING`s e cálculo/registro do RTT.                                                                                                                |
| **`message_router.py`**        | **Roteamento de Mensagens.** Recebe mensagens de _todos_ os `peer_connection` e decide se deve processar localmente (ex: `PONG`, `ACK`) ou encaminhar/difundir a mensagem (`SEND`, `PUB`). |
| **`p2p_client.py`**            | **Orquestrador Central.** Controla o fluxo de trabalho: agenda tarefas de registro/descoberta, inicia a reconciliação da rede e expõe os métodos para a CLI.                               |
| **`cli.py`**                   | **Interface de Usuário.** Lida com a entrada do usuário (`/msg`, `/pub`, `/quit`) e as traduz em ações do `p2p_client`.                                                                    |

---

## 🏃 Como Executar

**(Instruções a serem preenchidas após a implementação dos módulos de inicialização.)**

```bash
# Exemplo
$ python3 main.py --name alice --namespace CIC --port 7070
```

## Roteiro

https://github.com/mfcaetano/pyp2p-rdv

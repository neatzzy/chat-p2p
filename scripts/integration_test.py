#!/usr/bin/env python3
"""Integration test script for chat-p2p

This script:
- Starts two peer processes using `src/main.py start --name ... --port ...` (runs in background)
- Waits until both peers report they are listening
- Connects to each peer via a raw TCP socket, performs HELLO handshake, then sends a SEND message with `require_ack=True`
- Waits for the ACK and measures RTT
- Prints results and terminates the peer processes

Run from repository root (preferably inside the project's venv):

    python3 scripts/integration_test.py

"""

import subprocess
import sys
import time
import os
import socket
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'src'
LOGS = ROOT / 'logs'
LOGS.mkdir(exist_ok=True)

# Ports for the two test peers
PORT_A = 7080
PORT_B = 7081
HOST = '127.0.0.1'

PY = sys.executable
MAIN = str(SRC / 'main.py')

# Timeout settings
START_TIMEOUT = 15.0
HANDSHAKE_TIMEOUT = 5.0
ACK_TIMEOUT = 10.0


def start_peer(name: str, port: int, logfile: Path) -> subprocess.Popen:
    """Start a peer CLI process and return the Popen object."""
    cmd = [PY, MAIN, 'start', '--name', name, '--namespace', 'CIC', '--port', str(port)]
    f = open(logfile, 'w')
    p = subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT, text=True)
    return p


def wait_for_port(host: str, port: int, timeout: float = START_TIMEOUT) -> bool:
    """Wait until a TCP connection to host:port succeeds (peer is listening).

    Returns True if port accept connections within timeout, False otherwise.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except Exception:
            time.sleep(0.2)
    return False


def handshake_and_send(host: str, port: int, nick: str) -> dict:
    """Connect to peer server, perform HELLO handshake and send SEND requiring ACK.

    Returns a dict with outcome and rtt (seconds) or error.
    """
    result = {'peer': f'{host}:{port}', 'ok': False, 'rtt': None, 'error': None}

    try:
        s = socket.create_connection((host, port), timeout=HANDSHAKE_TIMEOUT)
        s.settimeout(HANDSHAKE_TIMEOUT)

        # Send HELLO
        hello = {
            'type': 'HELLO',
            'peer_id': f'probe_{nick}@local',
            'version': '1.0',
            'features': ['ack', 'metrics'],
            'ttl': 1,
        }
        s.sendall(json.dumps(hello).encode('utf-8') + b"\n")

        # Expect HELLO_OK or HELLO
        buf = b''
        start = time.time()
        while True:
            chunk = s.recv(4096)
            if not chunk:
                break
            buf += chunk
            if b'\n' in buf:
                break
            if time.time() - start > HANDSHAKE_TIMEOUT:
                raise TimeoutError('Handshake read timeout')

        if not buf:
            raise ConnectionError('No handshake response')

        msg, _sep, rest = buf.partition(b"\n")
        try:
            resp = json.loads(msg.decode('utf-8'))
        except Exception:
            raise ValueError(f'Invalid handshake response: {msg!r}')

        if resp.get('type') not in ('HELLO_OK', 'HELLO'):
            raise ValueError(f'Unexpected handshake type: {resp.get("type")}')

        # Now send a SEND message requiring ACK
        msg_id = f'test-{int(time.time()*1000)}'
        send_msg = {
            'type': 'SEND',
            'msg_id': msg_id,
            'src': hello['peer_id'],
            'dst': resp.get('peer_id', 'unknown'),
            'payload': f'Hello from {hello["peer_id"]}',
            'require_ack': True,
            'timestamp': time.time(),
            'ttl': 1,
        }

        # Send and wait for ACK
        s.sendall(json.dumps(send_msg).encode('utf-8') + b"\n")
        t0 = time.time()

        # Wait for ACK
        ack_buf = b''
        deadline = t0 + ACK_TIMEOUT
        while time.time() < deadline:
            try:
                chunk = s.recv(4096)
            except socket.timeout:
                continue
            if not chunk:
                break
            ack_buf += chunk
            while b'\n' in ack_buf:
                line, _, ack_buf = ack_buf.partition(b'\n')
                try:
                    ack = json.loads(line.decode('utf-8'))
                except Exception:
                    continue
                if ack.get('type') == 'ACK' and ack.get('msg_id') == msg_id:
                    rtt = time.time() - t0
                    result['ok'] = True
                    result['rtt'] = rtt
                    s.close()
                    return result
        result['error'] = 'ACK timeout'
        s.close()
        return result

    except Exception as e:
        result['error'] = str(e)
        return result


def main():
    log_a = LOGS / 'peerA.log'
    log_b = LOGS / 'peerB.log'

    print('Starting peers...')
    pA = start_peer('testA', PORT_A, log_a)
    pB = start_peer('testB', PORT_B, log_b)

    try:
        okA = wait_for_port(HOST, PORT_A, timeout=START_TIMEOUT)
        okB = wait_for_port(HOST, PORT_B, timeout=START_TIMEOUT)

        if not okA or not okB:
            print('One or both peers failed to start in time. See logs for details:')
            print(log_a, log_b)
            return 2

        print('Both peers listening, running handshake/send tests...')

        resA = handshake_and_send(HOST, PORT_A, 'A')
        resB = handshake_and_send(HOST, PORT_B, 'B')

        print('\nResults:')
        print('Peer A:', resA)
        print('Peer B:', resB)

        # Basic assertions
        success = 0
        if resA.get('ok'):
            print(f"PeerA ACK RTT: {resA['rtt']*1000:.2f} ms")
            success += 1
        else:
            print('PeerA test failed:', resA.get('error'))

        if resB.get('ok'):
            print(f"PeerB ACK RTT: {resB['rtt']*1000:.2f} ms")
            success += 1
        else:
            print('PeerB test failed:', resB.get('error'))

        return_code = 0 if success == 2 else 1
        return return_code

    finally:
        print('Shutting down peers...')
        try:
            pA.terminate()
        except Exception:
            pass
        try:
            pB.terminate()
        except Exception:
            pass
        # give them a moment and then kill if needed
        time.sleep(1)
        if pA.poll() is None:
            pA.kill()
        if pB.poll() is None:
            pB.kill()


if __name__ == '__main__':
    rc = main()
    sys.exit(rc)

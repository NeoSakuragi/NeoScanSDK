#!/usr/bin/env python3
"""
Test client for Digital simulator's TCP remote interface.
Connects to Digital, sets inputs on a simple OR gate, reads output.

Prerequisites:
  1. Open Digital (our modified build)
  2. Draw a circuit with: Input "A" (1 bit) → OR gate → Output "Y"
                          Input "B" (1 bit) →
  3. Name the inputs "A" and "B", output "Y"
  4. Enable remote port: Edit → Settings → check "Open Remote Port"
  5. Start simulation (play button)
  6. Run this script

Protocol: Java DataOutputStream.writeUTF / DataInputStream.readUTF
  - 2-byte big-endian length prefix, then UTF-8 string
"""

import socket
import struct
import sys
import time

HOST = 'localhost'
PORT = 41114

def send_cmd(sock, cmd):
    """Send a command using Java's writeUTF format"""
    encoded = cmd.encode('utf-8')
    sock.sendall(struct.pack('>H', len(encoded)) + encoded)

def recv_response(sock):
    """Read response using Java's readUTF format"""
    header = sock.recv(2)
    if len(header) < 2:
        return None
    length = struct.unpack('>H', header)[0]
    data = b''
    while len(data) < length:
        chunk = sock.recv(length - len(data))
        if not chunk:
            break
        data += chunk
    return data.decode('utf-8')

def digital_cmd(sock, cmd):
    """Send command, get response"""
    send_cmd(sock, cmd)
    resp = recv_response(sock)
    return resp

def main():
    print(f"Connecting to Digital at {HOST}:{PORT}...")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect((HOST, PORT))
    except ConnectionRefusedError:
        print("ERROR: Cannot connect. Make sure Digital is running with remote port enabled.")
        sys.exit(1)

    print("Connected!\n")

    # Read initial state
    resp = digital_cmd(sock, "measure")
    print(f"Initial state: {resp}\n")

    # Test OR gate truth table
    print("=== OR Gate Truth Table ===")
    print(f"{'A':>3s}  {'B':>3s}  {'Y (expected)':>12s}  {'Y (actual)':>10s}  {'Result':>6s}")
    print("-" * 45)

    for a in [0, 1]:
        for b in [0, 1]:
            expected = a | b

            # Set inputs
            digital_cmd(sock, f"set:A={a}")
            digital_cmd(sock, f"set:B={b}")

            # Read outputs
            resp = digital_cmd(sock, "measure")
            # Parse JSON: {"A":0,"B":0,"Y":0}
            # Simple parsing since it's flat JSON
            values = {}
            if resp and resp.startswith("ok:"):
                json_str = resp[3:]
                for pair in json_str.strip('{}').split(','):
                    k, v = pair.split(':')
                    values[k.strip('"')] = int(v)

            actual = values.get('Y', -1)
            status = "PASS" if actual == expected else "FAIL"
            print(f"{a:>3d}  {b:>3d}  {expected:>12d}  {actual:>10d}  {status:>6s}")

    print("\n=== Done ===")
    sock.close()

if __name__ == '__main__':
    main()

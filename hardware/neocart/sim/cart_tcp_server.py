#!/usr/bin/env python3
"""TCP server wrapping the Verilator P-ROM cart model via ctypes."""
import socket, struct, ctypes, os, sys

SIM_DIR = os.path.dirname(os.path.abspath(__file__))

class CartBridge:
    def __init__(self):
        lib_path = os.path.join(SIM_DIR, "libcart_bridge_shared.so")
        self.lib = ctypes.CDLL(lib_path)
        self.lib.cart_init.argtypes = [ctypes.c_char_p]
        self.lib.cart_init.restype = ctypes.c_int
        self.lib.cart_read.argtypes = [ctypes.c_uint32]
        self.lib.cart_read.restype = ctypes.c_uint16
        self.lib.cart_write.argtypes = [ctypes.c_uint32, ctypes.c_uint16]
        self.lib.cart_write.restype = None
        self.lib.cart_init(b"")
        self.last_addr = 0
        self.last_data = 0
        self.bank = 0

    def read(self, addr):
        self.last_addr = addr
        self.last_data = self.lib.cart_read(addr)
        return self.last_data

    def write(self, addr, data):
        self.lib.cart_write(addr, data)
        if addr == 0x2FFFF0:
            self.bank = data & 7

def send_resp(conn, msg):
    encoded = msg.encode('utf-8')
    conn.sendall(struct.pack('>H', len(encoded)) + encoded)

def recv_cmd(conn):
    header = conn.recv(2)
    if len(header) < 2: return None
    length = struct.unpack('>H', header)[0]
    data = b''
    while len(data) < length:
        chunk = conn.recv(length - len(data))
        if not chunk: return None
        data += chunk
    return data.decode('utf-8')

def handle_client(conn, cart):
    while True:
        cmd = recv_cmd(conn)
        if cmd is None: break
        try:
            if cmd == "measure":
                send_resp(conn, f'ok:{{"addr":{cart.last_addr},"data":{cart.last_data},"bank":{cart.bank}}}')
            elif cmd.startswith("read:"):
                data = cart.read(int(cmd[5:], 0))
                send_resp(conn, f"ok:{data}")
            elif cmd.startswith("write:"):
                a, d = cmd[6:].split("=")
                cart.write(int(a, 0), int(d, 0))
                send_resp(conn, "ok")
            elif cmd == "stop":
                send_resp(conn, "ok"); break
            else:
                send_resp(conn, f"error:unknown '{cmd}'")
        except Exception as e:
            send_resp(conn, f"error:{e}")

def main():
    cart = CartBridge()
    print(f"Self-test: read(0x000000)=0x{cart.read(0):04X} read(0x000002)=0x{cart.read(2):04X}")

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(('0.0.0.0', 41114))
    srv.listen(1)
    print("Cart TCP server on port 41114")

    while True:
        conn, addr = srv.accept()
        print(f"Client: {addr}")
        handle_client(conn, cart)
        conn.close()

if __name__ == '__main__':
    main()

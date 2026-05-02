#!/usr/bin/env python3
"""NeoCart SHM Server — GUI with gold finger visualization.

Loads a .neo file and serves ROM data through shared memory,
displaying the MVS cart edge connector pins in real time.

4-phase handshake:
  1. MAME: addr→[0..2], type→[3], AS=1
  2. Cart: reads addr, data→[4..5], DTACK=1
  3. MAME: reads data, AS=0
  4. Cart: DTACK=0
"""
import tkinter as tk
from tkinter import filedialog, ttk
import mmap, struct, os, threading, time, ctypes

SHM_PATH = "/dev/shm/neocart_rom"
SHM_SIZE = 16
NEO_HEADER = 4096

BUS_NAMES = ["P-ROM", "C-ROM", "S-ROM", "M-ROM", "V-ROM"]
PIN_HIGH = "#00ff00"
PIN_LOW = "#1a1a1a"
PIN_ADDR = "#00aaff"
PIN_DATA = "#ffaa00"

class NeoCart:
    def __init__(self):
        self.prom = self.srom = self.mrom = self.v1rom = self.v2rom = self.crom = None
        self.p_size = self.s_size = self.m_size = self.v1_size = self.v2_size = self.c_size = 0
        self.name = ""

    def load_neo(self, path):
        with open(path, 'rb') as f:
            hdr = f.read(NEO_HEADER)
            if hdr[:3] != b'NEO':
                raise ValueError("Not a .neo file")
            self.p_size  = struct.unpack_from('<I', hdr, 4)[0]
            self.s_size  = struct.unpack_from('<I', hdr, 8)[0]
            self.m_size  = struct.unpack_from('<I', hdr, 12)[0]
            self.v1_size = struct.unpack_from('<I', hdr, 16)[0]
            self.v2_size = struct.unpack_from('<I', hdr, 20)[0]
            self.c_size  = struct.unpack_from('<I', hdr, 24)[0]
            self.name = hdr[0x2C:0x4C].split(b'\x00')[0].decode(errors='replace')

            self.prom  = f.read(self.p_size)
            self.srom  = f.read(self.s_size) if self.s_size else b''
            self.mrom  = f.read(self.m_size) if self.m_size else b''
            self.v1rom = f.read(self.v1_size) if self.v1_size else b''
            self.v2rom = f.read(self.v2_size) if self.v2_size else b''
            self.crom  = f.read(self.c_size) if self.c_size else b''

        # P-ROM as uint16 array
        self.prom16 = memoryview(bytearray(self.prom)).cast('H')

    def read(self, addr, bus_type):
        if bus_type == 0:  # P-ROM word
            idx = addr // 2
            return self.prom16[idx] if idx < len(self.prom16) else 0xFFFF
        elif bus_type == 1:  # C-ROM byte
            return self.crom[addr] if addr < self.c_size else 0
        elif bus_type == 2:  # S-ROM byte
            return self.srom[addr] if addr < self.s_size else 0
        elif bus_type == 3:  # M-ROM byte
            return self.mrom[addr] if addr < self.m_size else 0
        elif bus_type == 4:  # V-ROM byte
            return self.v1rom[addr] if addr < self.v1_size else 0
        return 0


class SHMBus:
    def __init__(self):
        self.shm = None
        self.raw = None

    def open(self):
        fd = os.open(SHM_PATH, os.O_CREAT | os.O_RDWR, 0o666)
        os.ftruncate(fd, SHM_SIZE)
        self.shm = mmap.mmap(fd, SHM_SIZE)
        os.close(fd)
        self.raw = (ctypes.c_uint8 * SHM_SIZE).from_buffer(self.shm)
        self.raw[6] = 0
        self.raw[7] = 0

    def close(self):
        if self.shm:
            self.shm.close()
            try: os.unlink(SHM_PATH)
            except: pass

    def get_state(self):
        """Read current bus state for display."""
        addr = self.raw[0] | (self.raw[1] << 8) | (self.raw[2] << 16)
        bus_type = self.raw[3]
        data = self.raw[4] | (self.raw[5] << 8)
        as_pin = self.raw[6]
        dtack = self.raw[7]
        return addr, bus_type, data, as_pin, dtack


class ServerThread(threading.Thread):
    def __init__(self, cart, bus):
        super().__init__(daemon=True)
        self.cart = cart
        self.bus = bus
        self.running = False
        self.step_mode = False
        self.step_event = threading.Event()
        self.cycle_count = 0
        self.last_addr = 0
        self.last_type = 0
        self.last_data = 0

    def run(self):
        raw = self.bus.raw
        self.running = True
        while self.running:
            # Step mode: wait for step signal
            if self.step_mode:
                self.step_event.wait()
                self.step_event.clear()
                if not self.running:
                    break

            # Phase 2: wait for AS=1
            while raw[6] == 0 and self.running:
                pass
            if not self.running:
                break

            # Read address and type
            addr = raw[0] | (raw[1] << 8) | (raw[2] << 16)
            bus_type = raw[3]

            # Lookup data
            data = self.cart.read(addr, bus_type)

            # Put data on bus, assert DTACK
            raw[4] = data & 0xFF
            raw[5] = (data >> 8) & 0xFF
            ctypes.c_uint8.__init__  # memory barrier workaround
            raw[7] = 1  # DTACK = 1

            # Phase 4: wait for AS=0
            while raw[6] != 0 and self.running:
                pass

            # Deassert DTACK
            raw[7] = 0

            self.last_addr = addr
            self.last_type = bus_type
            self.last_data = data
            self.cycle_count += 1

    def stop(self):
        self.running = False
        self.step_event.set()

    def step(self):
        self.step_event.set()


class NeoCartGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("NeoCart SHM Server")
        self.root.geometry("900x700")
        self.root.configure(bg='#0a0a0a')

        self.cart = NeoCart()
        self.bus = SHMBus()
        self.server = None

        self._build_ui()
        self._update_display()

    def _build_ui(self):
        # Top bar: controls
        ctrl = tk.Frame(self.root, bg='#1a1a1a', pady=5)
        ctrl.pack(fill=tk.X)

        tk.Button(ctrl, text="Load .neo", command=self._load_neo,
                  bg='#333', fg='white').pack(side=tk.LEFT, padx=5)
        self.btn_start = tk.Button(ctrl, text="Start", command=self._start,
                                   bg='#333', fg='white', state=tk.DISABLED)
        self.btn_start.pack(side=tk.LEFT, padx=5)
        self.btn_stop = tk.Button(ctrl, text="Stop", command=self._stop,
                                  bg='#333', fg='white', state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, padx=5)

        self.step_var = tk.BooleanVar()
        tk.Checkbutton(ctrl, text="Step mode", variable=self.step_var,
                       bg='#1a1a1a', fg='white', selectcolor='#333',
                       command=self._toggle_step).pack(side=tk.LEFT, padx=10)
        self.btn_step = tk.Button(ctrl, text="Step ▶", command=self._step,
                                  bg='#333', fg='white', state=tk.DISABLED)
        self.btn_step.pack(side=tk.LEFT, padx=5)

        self.lbl_game = tk.Label(ctrl, text="No game loaded", bg='#1a1a1a',
                                 fg='#888', font=('monospace', 10))
        self.lbl_game.pack(side=tk.RIGHT, padx=10)

        # Main area: cart visualization
        main = tk.Frame(self.root, bg='#0a0a0a')
        main.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Cart canvas
        self.canvas = tk.Canvas(main, bg='#0d0d0d', width=860, height=400,
                                highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Bottom: bus state display
        bus_frame = tk.Frame(self.root, bg='#111')
        bus_frame.pack(fill=tk.X, padx=10, pady=5)

        self.lbl_bus = tk.Label(bus_frame, text="BUS IDLE", bg='#111',
                                fg='#0f0', font=('monospace', 14), anchor='w')
        self.lbl_bus.pack(fill=tk.X, padx=5, pady=2)

        self.lbl_stats = tk.Label(bus_frame, text="Cycles: 0", bg='#111',
                                  fg='#888', font=('monospace', 10), anchor='w')
        self.lbl_stats.pack(fill=tk.X, padx=5)

        # Pin state labels
        pin_frame = tk.Frame(self.root, bg='#111')
        pin_frame.pack(fill=tk.X, padx=10, pady=(0, 10))

        self.pin_labels = {}
        pin_names = ["/AS", "/DTACK"]
        for name in pin_names:
            f = tk.Frame(pin_frame, bg='#111')
            f.pack(side=tk.LEFT, padx=10)
            tk.Label(f, text=name, bg='#111', fg='#888',
                     font=('monospace', 9)).pack()
            lbl = tk.Label(f, text="0", bg=PIN_LOW, fg='white',
                           font=('monospace', 12, 'bold'), width=3)
            lbl.pack()
            self.pin_labels[name] = lbl

        self._draw_cart()

    def _draw_cart(self):
        c = self.canvas
        c.delete("all")

        # Cart body
        cx, cy = 430, 200
        # PCB
        c.create_rectangle(80, 30, 780, 300, fill='#1a3a1a', outline='#2a5a2a', width=2)
        c.create_text(430, 50, text="NEO-GEO MVS CARTRIDGE", fill='#3a7a3a',
                      font=('monospace', 12, 'bold'))
        c.create_text(430, 70, text=self.cart.name or "(no game)",
                      fill='#5aba5a', font=('monospace', 10))

        # Gold finger rows — address bus (top row)
        self.addr_pins = []
        x0 = 100
        for i in range(24):
            x = x0 + i * 27
            pin = c.create_rectangle(x, 310, x+20, 345, fill=PIN_LOW, outline='#555')
            c.create_text(x+10, 355, text=f"A{i}", fill='#666',
                          font=('monospace', 7))
            self.addr_pins.append(pin)

        # Gold finger rows — data bus (middle row)
        self.data_pins = []
        for i in range(16):
            x = x0 + 108 + i * 27
            pin = c.create_rectangle(x, 365, x+20, 400, fill=PIN_LOW, outline='#555')
            c.create_text(x+10, 410, text=f"D{i}", fill='#666',
                          font=('monospace', 7))
            self.data_pins.append(pin)

        # Control pins
        self.ctrl_pins = {}
        ctrl_names = ["/AS", "/DTACK", "TYPE"]
        for i, name in enumerate(ctrl_names):
            x = x0 + i * 60
            pin = c.create_rectangle(x, 420, x+50, 445, fill=PIN_LOW, outline='#555')
            c.create_text(x+25, 455, text=name, fill='#666',
                          font=('monospace', 8))
            self.ctrl_pins[name] = pin

        # ROM size info
        y = 100
        for label, sz in [("P-ROM", self.cart.p_size), ("C-ROM", self.cart.c_size),
                          ("S-ROM", self.cart.s_size), ("M-ROM", self.cart.m_size),
                          ("V-ROM", self.cart.v1_size)]:
            if sz > 0:
                txt = f"{label}: {sz//1024}KB" if sz < 1024*1024 else f"{label}: {sz//1024//1024}MB"
                c.create_text(150, y, text=txt, fill='#5a8a5a', font=('monospace', 9), anchor='w')
                y += 18

    def _update_pins(self, addr, bus_type, data, as_pin, dtack):
        c = self.canvas

        # Address pins
        for i in range(24):
            bit = (addr >> i) & 1
            color = PIN_ADDR if bit else PIN_LOW
            c.itemconfig(self.addr_pins[i], fill=color)

        # Data pins
        for i in range(16):
            bit = (data >> i) & 1
            color = PIN_DATA if bit else PIN_LOW
            c.itemconfig(self.data_pins[i], fill=color)

        # Control pins
        c.itemconfig(self.ctrl_pins["/AS"],
                     fill=PIN_HIGH if as_pin else PIN_LOW)
        c.itemconfig(self.ctrl_pins["/DTACK"],
                     fill=PIN_HIGH if dtack else PIN_LOW)
        c.itemconfig(self.ctrl_pins["TYPE"],
                     fill='#ff6600' if bus_type > 0 else PIN_ADDR)

        # Pin state labels
        self.pin_labels["/AS"].config(text=str(as_pin),
                                       bg=PIN_HIGH if as_pin else PIN_LOW)
        self.pin_labels["/DTACK"].config(text=str(dtack),
                                          bg=PIN_HIGH if dtack else PIN_LOW)

    def _update_display(self):
        if self.server and self.server.running:
            addr = self.server.last_addr
            btype = self.server.last_type
            data = self.server.last_data
            cycles = self.server.cycle_count

            bus_name = BUS_NAMES[btype] if btype < len(BUS_NAMES) else "?"
            self.lbl_bus.config(
                text=f"{bus_name}  ADDR: 0x{addr:06X}  DATA: 0x{data:04X}")
            self.lbl_stats.config(text=f"Cycles: {cycles:,}")

            # Get live pin state from SHM
            if self.bus.raw:
                shm_addr, shm_type, shm_data, shm_as, shm_dtack = self.bus.get_state()
                self._update_pins(shm_addr, shm_type, shm_data, shm_as, shm_dtack)

        self.root.after(16, self._update_display)  # ~60fps GUI update

    def _load_neo(self):
        path = filedialog.askopenfilename(
            title="Load .neo ROM",
            initialdir="/data/roms",
            filetypes=[("Neo Geo ROM", "*.neo"), ("All files", "*.*")])
        if path:
            self.cart.load_neo(path)
            self.lbl_game.config(text=self.cart.name)
            self._draw_cart()
            self.btn_start.config(state=tk.NORMAL)

    def _start(self):
        self.bus.open()
        self.server = ServerThread(self.cart, self.bus)
        self.server.step_mode = self.step_var.get()
        self.server.start()
        self.btn_start.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        if self.step_var.get():
            self.btn_step.config(state=tk.NORMAL)

    def _stop(self):
        if self.server:
            self.server.stop()
            self.server.join(timeout=1)
            self.server = None
        self.bus.close()
        self.btn_start.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)
        self.btn_step.config(state=tk.DISABLED)

    def _toggle_step(self):
        if self.server:
            self.server.step_mode = self.step_var.get()
            self.btn_step.config(
                state=tk.NORMAL if self.step_var.get() else tk.DISABLED)

    def _step(self):
        if self.server:
            self.server.step()

    def run(self):
        self.root.mainloop()
        self._stop()


if __name__ == '__main__':
    import sys
    app = NeoCartGUI()
    # Auto-load if argument provided
    if len(sys.argv) > 1:
        app.cart.load_neo(sys.argv[1])
        app.lbl_game.config(text=app.cart.name)
        app._draw_cart()
        app.btn_start.config(state=tk.NORMAL)
    app.run()

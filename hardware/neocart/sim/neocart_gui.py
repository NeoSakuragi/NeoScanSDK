#!/usr/bin/env python3
"""NeoCart SHM Bus Monitor — reads the 32-byte pin-accurate SHM and displays
all gold finger signals in real time. Launches the C server as a subprocess.

Usage: python3 neocart_gui.py [game.neo]
"""
import tkinter as tk
from tkinter import filedialog
import mmap, struct, os, subprocess, signal, sys, ctypes

SHM_PATH = "/dev/shm/neocart_bus"
SHM_SIZE = 32
SERVER_BIN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shm_server")
MAME_BIN = os.path.expanduser("~/CLProjects/mame/neogeo")

COL_LOW  = "#111111"
COL_BG   = "#0a0a0a"
COL_PCB  = "#0d2a0d"
COL_TEXT = "#888888"

# ROM family colors
COL_P = "#00ff44"   # P-ROM green
COL_V = "#44aaff"   # V-ROM blue
COL_C = "#ffaa00"   # C-ROM orange
COL_S = "#ff66ff"   # S-ROM pink
COL_M = "#ffff44"   # M-ROM yellow

PROG_PINS = [
    # P-ROM address (green)
    ("A1",0,0,0,COL_P),("A2",0,1,0,COL_P),("A3",0,2,0,COL_P),("A4",0,3,0,COL_P),
    ("A5",0,4,0,COL_P),("A6",0,5,0,COL_P),("A7",0,6,0,COL_P),("A8",0,7,0,COL_P),
    ("A9",1,0,0,COL_P),("A10",1,1,0,COL_P),("A11",1,2,0,COL_P),("A12",1,3,0,COL_P),
    ("A13",1,4,0,COL_P),("A14",1,5,0,COL_P),("A15",1,6,0,COL_P),("A16",1,7,0,COL_P),
    ("A17",2,0,0,COL_P),("A18",2,1,0,COL_P),("A19",2,2,0,COL_P),
    # P-ROM / V-ROM control
    ("ROMOE",3,0,0,COL_P),("ROMOEU",3,1,0,COL_P),("ROMOEL",3,2,0,COL_P),("VROMOE",3,3,0,COL_V),
    # P-ROM data (green)
    ("D0",4,0,1,COL_P),("D1",4,1,1,COL_P),("D2",4,2,1,COL_P),("D3",4,3,1,COL_P),
    ("D4",4,4,1,COL_P),("D5",4,5,1,COL_P),("D6",4,6,1,COL_P),("D7",4,7,1,COL_P),
    ("D8",5,0,1,COL_P),("D9",5,1,1,COL_P),("D10",5,2,1,COL_P),("D11",5,3,1,COL_P),
    ("D12",5,4,1,COL_P),("D13",5,5,1,COL_P),("D14",5,6,1,COL_P),("D15",5,7,1,COL_P),
    # Acknowledge
    ("DTACK",10,0,1,COL_P),("VDTACK",10,1,1,COL_V),
]

CHA_PINS = [
    # C-ROM address (orange)
    ("P0",12,0,0,COL_C),("P1",12,1,0,COL_C),("P2",12,2,0,COL_C),("P3",12,3,0,COL_C),
    ("P4",12,4,0,COL_C),("P5",12,5,0,COL_C),("P6",12,6,0,COL_C),("P7",12,7,0,COL_C),
    ("P8",13,0,0,COL_C),("P9",13,1,0,COL_C),("P10",13,2,0,COL_C),("P11",13,3,0,COL_C),
    ("P12",13,4,0,COL_C),("P13",13,5,0,COL_C),("P14",13,6,0,COL_C),("P15",13,7,0,COL_C),
    ("P16",14,0,0,COL_C),("P17",14,1,0,COL_C),("P18",14,2,0,COL_C),("P19",14,3,0,COL_C),
    ("P20",14,4,0,COL_C),("P21",14,5,0,COL_C),("P22",14,6,0,COL_C),("P23",14,7,0,COL_C),
    # Control — each in its family color
    ("PCK1B",15,0,0,COL_C),("PCK2B",15,1,0,COL_C),("SDMRD",15,2,0,COL_S),("MROMOE",15,3,0,COL_M),
    # C-ROM data (orange)
    ("CR0",16,0,1,COL_C),("CR1",16,1,1,COL_C),("CR2",16,2,1,COL_C),("CR3",16,3,1,COL_C),
    ("CR4",16,4,1,COL_C),("CR5",16,5,1,COL_C),("CR6",16,6,1,COL_C),("CR7",16,7,1,COL_C),
    # S-ROM address (pink)
    ("SDA0",20,0,0,COL_S),("SDA1",20,1,0,COL_S),("SDA2",20,2,0,COL_S),("SDA3",20,3,0,COL_S),
    ("SDA4",20,4,0,COL_S),("SDA5",20,5,0,COL_S),("SDA6",20,6,0,COL_S),("SDA7",20,7,0,COL_S),
    # S-ROM data (pink)
    ("SDD0",29,0,1,COL_S),("SDD1",29,1,1,COL_S),("SDD2",29,2,1,COL_S),("SDD3",29,3,1,COL_S),
    ("SDD4",29,4,1,COL_S),("SDD5",29,5,1,COL_S),("SDD6",29,6,1,COL_S),("SDD7",29,7,1,COL_S),
    # Acknowledge — each in its family color
    ("CDTACK",27,0,1,COL_C),("SDTACK",27,1,1,COL_S),("MDTACK",27,2,1,COL_M),
]


class NeoCartGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("NeoCart Bus Monitor")
        self.root.geometry("1100x750")
        self.root.configure(bg=COL_BG)

        self.shm = None
        self.shm_rw = None
        self.raw = None
        self.server_proc = None
        self.neo_path = None
        self.paused = False

        self._build_ui()
        self._poll()

    def _build_ui(self):
        # Top controls
        ctrl = tk.Frame(self.root, bg='#1a1a1a', pady=4)
        ctrl.pack(fill=tk.X)

        tk.Button(ctrl, text="Load .neo", command=self._load_neo,
                  bg='#333', fg='white', padx=8).pack(side=tk.LEFT, padx=4)
        self.btn_start = tk.Button(ctrl, text="Start Server", command=self._start_server,
                                   bg='#333', fg='white', state=tk.DISABLED, padx=8)
        self.btn_start.pack(side=tk.LEFT, padx=4)
        self.btn_stop = tk.Button(ctrl, text="Stop", command=self._stop_server,
                                  bg='#333', fg='white', state=tk.DISABLED, padx=8)
        self.btn_stop.pack(side=tk.LEFT, padx=4)
        self.btn_mame = tk.Button(ctrl, text="Launch MAME", command=self._launch_mame,
                                  bg='#333', fg='white', state=tk.DISABLED, padx=8)
        self.btn_mame.pack(side=tk.LEFT, padx=4)

        sep = tk.Frame(ctrl, bg='#444', width=2)
        sep.pack(side=tk.LEFT, fill=tk.Y, padx=8)

        self.btn_pause = tk.Button(ctrl, text="Pause", command=self._pause,
                                    bg='#553300', fg='white', padx=8, state=tk.DISABLED)
        self.btn_pause.pack(side=tk.LEFT, padx=4)
        self.btn_step = tk.Button(ctrl, text="Step", command=self._step,
                                   bg='#553300', fg='white', padx=8, state=tk.DISABLED)
        self.btn_step.pack(side=tk.LEFT, padx=4)
        self.btn_resume = tk.Button(ctrl, text="Resume", command=self._resume,
                                     bg='#335500', fg='white', padx=8, state=tk.DISABLED)
        self.btn_resume.pack(side=tk.LEFT, padx=4)

        self.lbl_game = tk.Label(ctrl, text="No game loaded", bg='#1a1a1a',
                                 fg=COL_TEXT, font=('monospace', 10))
        self.lbl_game.pack(side=tk.RIGHT, padx=10)

        # Main area — two connector panels
        main = tk.Frame(self.root, bg=COL_BG)
        main.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        # PROG connector
        self.prog_frame = tk.LabelFrame(main, text=" PROG (CTRG2) — P-ROM + V-ROM ",
                                         bg=COL_PCB, fg='#5a5', font=('monospace', 10, 'bold'),
                                         padx=6, pady=4)
        self.prog_frame.pack(fill=tk.X, pady=2)
        self.prog_pin_widgets = self._build_pin_row(self.prog_frame, PROG_PINS)

        # CHA connector
        self.cha_frame = tk.LabelFrame(main, text=" CHA (CTRG1) — C-ROM + S-ROM + M-ROM ",
                                        bg=COL_PCB, fg='#5a5', font=('monospace', 10, 'bold'),
                                        padx=6, pady=4)
        self.cha_frame.pack(fill=tk.X, pady=2)
        self.cha_pin_widgets = self._build_pin_row(self.cha_frame, CHA_PINS)

        # Bus state readout — one line per ROM type
        bus_frame = tk.Frame(self.root, bg='#111', pady=6)
        bus_frame.pack(fill=tk.X, padx=8, pady=4)

        self.rom_labels = {}
        for name, color in [("P-ROM", "#00ff44"), ("V-ROM", "#44aaff"),
                             ("C-ROM", "#ffaa00"), ("S-ROM", "#ff66ff"), ("M-ROM", "#ffff44")]:
            lbl = tk.Label(bus_frame, text=f"{name}: idle", bg='#111',
                           fg=color, font=('monospace', 11), anchor='w')
            lbl.pack(fill=tk.X, padx=6)
            self.rom_labels[name] = lbl

        self.lbl_status = tk.Label(bus_frame, text="Server: stopped", bg='#111',
                                    fg=COL_TEXT, font=('monospace', 9), anchor='w')
        self.lbl_status.pack(fill=tk.X, padx=6)


    def _build_pin_row(self, parent, pins):
        widgets = []
        row = tk.Frame(parent, bg=COL_PCB)
        row.pack(fill=tk.X)
        for i, (name, byte_off, bit, is_out, col_hi) in enumerate(pins):
            if i > 0 and i % 24 == 0:
                row = tk.Frame(parent, bg=COL_PCB)
                row.pack(fill=tk.X, pady=1)
            f = tk.Frame(row, bg=COL_PCB, padx=1)
            f.pack(side=tk.LEFT, padx=1, pady=1)
            sz = 32
            c = tk.Canvas(f, width=sz, height=sz, bg=COL_PCB, highlightthickness=0)
            c.pack()
            # Determine pin type from name and direction
            is_ctrl = name in ('ROMOE','ROMOEU','ROMOEL','VROMOE','PCK1B','PCK2B',
                               'SDMRD','MROMOE','DTACK','VDTACK','CDTACK','SDTACK','MDTACK')
            if is_ctrl and not is_out:
                # System control → circle (MVS drives)
                shape = c.create_oval(2, 2, sz-2, sz-2, fill=COL_LOW, outline='#333')
            elif is_ctrl and is_out:
                # Cart control → diamond
                mid = sz//2
                shape = c.create_polygon(mid,1, sz-2,mid, mid,sz-2, 2,mid,
                                          fill=COL_LOW, outline='#333')
            elif not is_out:
                # System→Cart data (address) → triangle down
                shape = c.create_polygon(2,2, sz-2,2, sz//2,sz-2,
                                          fill=COL_LOW, outline='#333')
            else:
                # Cart→System data (response) → triangle up
                shape = c.create_polygon(sz//2,2, sz-2,sz-2, 2,sz-2,
                                          fill=COL_LOW, outline='#333')
            lbl = tk.Label(f, text=name, bg=COL_PCB, fg=COL_TEXT,
                           font=('monospace', 5))
            lbl.pack()
            widgets.append((c, shape, byte_off, bit, col_hi))
        return widgets

    def _update_pins(self, widgets):
        if not self.raw:
            return
        for canvas, shape, byte_off, bit, col_hi in widgets:
            if byte_off < SHM_SIZE:
                val = (self.raw[byte_off] >> bit) & 1
                canvas.itemconfig(shape, fill=col_hi if val else COL_LOW)

    def _poll(self):
        if self.shm and self.raw:
            self._update_pins(self.prog_pin_widgets)
            self._update_pins(self.cha_pin_widgets)

            # P-ROM
            paddr = self.raw[0] | (self.raw[1]<<8) | ((self.raw[2]&0x07)<<16)
            pdata = self.raw[4] | (self.raw[5]<<8)
            romoe = not (self.raw[3] & 0x01)
            pdtack = not (self.raw[10] & 0x01)
            if romoe or pdtack:
                self.rom_labels["P-ROM"].config(text=f"P-ROM  ADDR 0x{paddr:06X}  DATA 0x{pdata:04X}  /OE {'*' if romoe else '-'}  /DTACK {'*' if pdtack else '-'}")
            else:
                self.rom_labels["P-ROM"].config(text=f"P-ROM  idle")

            # V-ROM
            vaddr = self.raw[6] | (self.raw[7]<<8) | (self.raw[8]<<16)
            vdata = self.raw[9]
            vromoe = not (self.raw[3] & 0x08)
            vdtack = not (self.raw[10] & 0x02)
            if vromoe or vdtack:
                self.rom_labels["V-ROM"].config(text=f"V-ROM  ADDR 0x{vaddr:06X}  DATA 0x{vdata:02X}  /OE {'*' if vromoe else '-'}  /DTACK {'*' if vdtack else '-'}")
            else:
                self.rom_labels["V-ROM"].config(text=f"V-ROM  idle")

            # C-ROM
            caddr = self.raw[12] | (self.raw[13]<<8) | (self.raw[14]<<16) | (self.raw[28]<<24)
            cdata = self.raw[16] | (self.raw[17]<<8)
            pck1b = not (self.raw[15] & 0x01)
            cdtack = not (self.raw[27] & 0x01)
            if pck1b or cdtack:
                self.rom_labels["C-ROM"].config(text=f"C-ROM  ADDR 0x{caddr:07X}  DATA 0x{cdata:04X}  /PCK1B {'*' if pck1b else '-'}  /DTACK {'*' if cdtack else '-'}")
            else:
                self.rom_labels["C-ROM"].config(text=f"C-ROM  idle")

            # S-ROM
            saddr = self.raw[20] | (self.raw[21]<<8) | (self.raw[22]<<16)
            sdata = self.raw[29]
            sromoe = not (self.raw[15] & 0x04)
            sdtack = not (self.raw[27] & 0x02)
            if sromoe or sdtack:
                self.rom_labels["S-ROM"].config(text=f"S-ROM  ADDR 0x{saddr:05X}  DATA 0x{sdata:02X}  /SDMRD {'*' if sromoe else '-'}  /DTACK {'*' if sdtack else '-'}")
            else:
                self.rom_labels["S-ROM"].config(text=f"S-ROM  idle")

            # M-ROM
            maddr = self.raw[23] | (self.raw[24]<<8) | ((self.raw[25]&1)<<16)
            mdata = self.raw[26]
            mromoe = not (self.raw[15] & 0x08)
            mdtack = not (self.raw[27] & 0x04)
            if mromoe or mdtack:
                self.rom_labels["M-ROM"].config(text=f"M-ROM  ADDR 0x{maddr:05X}  DATA 0x{mdata:02X}  /OE {'*' if mromoe else '-'}  /DTACK {'*' if mdtack else '-'}")
            else:
                self.rom_labels["M-ROM"].config(text=f"M-ROM  idle")

        self.root.after(16, self._poll)  # ~60fps

    def _try_open_shm(self):
        try:
            fd = os.open(SHM_PATH, os.O_RDWR)
            self.shm = mmap.mmap(fd, SHM_SIZE, access=mmap.ACCESS_READ)
            os.close(fd)
            fd2 = os.open(SHM_PATH, os.O_RDWR)
            self.shm_rw = mmap.mmap(fd2, SHM_SIZE)
            os.close(fd2)
            self.raw = (ctypes.c_uint8 * SHM_SIZE).from_buffer_copy(b'\x00' * SHM_SIZE)
            self.root.after(100, self._read_shm)
            return True
        except:
            return False

    def _read_shm(self):
        if self.shm:
            try:
                self.shm.seek(0)
                data = self.shm.read(SHM_SIZE)
                ctypes.memmove(self.raw, data, SHM_SIZE)
            except:
                pass
        self.root.after(16, self._read_shm)

    def _load_neo(self):
        path = filedialog.askopenfilename(
            title="Load .neo ROM",
            initialdir="/data/roms",
            filetypes=[("Neo Geo ROM", "*.neo"), ("All files", "*.*")])
        if path:
            self.neo_path = path
            name = os.path.basename(path).replace('.neo', '')
            self.lbl_game.config(text=name)
            self.btn_start.config(state=tk.NORMAL)

    def _start_server(self):
        if not self.neo_path:
            return
        self._stop_server()
        self.server_proc = subprocess.Popen(
            [SERVER_BIN, self.neo_path],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.root.after(500, self._try_open_shm)
        self.btn_start.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self.btn_mame.config(state=tk.NORMAL)
        self.btn_pause.config(state=tk.NORMAL)
        self.lbl_status.config(text=f"Server: running (PID {self.server_proc.pid})")

    def _stop_server(self):
        if self.server_proc:
            self.server_proc.send_signal(signal.SIGINT)
            try: self.server_proc.wait(timeout=2)
            except: self.server_proc.kill()
            self.server_proc = None
        if self.shm:
            self.shm.close()
            self.shm = None
            self.raw = None
        self.btn_start.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)
        self.btn_mame.config(state=tk.DISABLED)
        self.lbl_status.config(text="Server: stopped")

    def _pause(self):
        if self.shm_rw:
            self.shm_rw[30] = 1
            self.paused = True
            self.btn_pause.config(state=tk.DISABLED)
            self.btn_step.config(state=tk.NORMAL)
            self.btn_resume.config(state=tk.NORMAL)
            self.lbl_status.config(text="Server: PAUSED")

    def _step(self):
        if self.shm_rw and self.paused:
            self.shm_rw[31] = 1

    def _resume(self):
        if self.shm_rw:
            self.shm_rw[30] = 0
            self.paused = False
            self.btn_pause.config(state=tk.NORMAL)
            self.btn_step.config(state=tk.DISABLED)
            self.btn_resume.config(state=tk.DISABLED)
            self.lbl_status.config(text=f"Server: running")

    def _launch_mame(self):
        subprocess.Popen([
            MAME_BIN, "neocart",
            "-rompath", os.path.expanduser("~/NeoGeo/roms"),
            "-bios", "unibios40",
            "-skip_gameinfo", "-window", "-nomaximize"
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def run(self):
        # Auto-load if argument provided
        if len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
            self.neo_path = sys.argv[1]
            self.lbl_game.config(text=os.path.basename(sys.argv[1]).replace('.neo',''))
            self.btn_start.config(state=tk.NORMAL)
        self.root.mainloop()
        self._stop_server()


if __name__ == '__main__':
    NeoCartGUI().run()

#!/usr/bin/env python3
"""NeoCart SHM Bus Monitor — reads the 32-byte pin-accurate SHM and displays
all gold finger signals in real time. Launches the C server as a subprocess.

Usage: python3 neocart_gui.py [game.neo]
"""
import tkinter as tk
from tkinter import filedialog
import mmap, struct, os, subprocess, signal, sys, ctypes

SHM_PATH = "/dev/shm/neocart_bus"
SHM_SIZE = 448  # 7 x 64-byte cache lines

# Cache line offsets
PROG_BASE = 0
CROM_BASE = 64
SROM_BASE = 128
MROM_BASE = 192
VROM_BASE = 320
DBG_BASE  = 384
SERVER_BIN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shm_server")
NEOSCAN_EMU = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "../emu/neogeo_sdl"))

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
    ("DTACK",6,0,1,COL_P),("VDTACK",325,0,1,COL_V),
]

CHA_PINS = [
    # C-ROM address (orange) — cache line 1
    ("P0",64,0,0,COL_C),("P1",64,1,0,COL_C),("P2",64,2,0,COL_C),("P3",64,3,0,COL_C),
    ("P4",64,4,0,COL_C),("P5",64,5,0,COL_C),("P6",64,6,0,COL_C),("P7",64,7,0,COL_C),
    ("P8",65,0,0,COL_C),("P9",65,1,0,COL_C),("P10",65,2,0,COL_C),("P11",65,3,0,COL_C),
    ("P12",65,4,0,COL_C),("P13",65,5,0,COL_C),("P14",65,6,0,COL_C),("P15",65,7,0,COL_C),
    ("P16",66,0,0,COL_C),("P17",66,1,0,COL_C),("P18",66,2,0,COL_C),("P19",66,3,0,COL_C),
    ("P20",66,4,0,COL_C),("P21",66,5,0,COL_C),("P22",66,6,0,COL_C),("P23",66,7,0,COL_C),
    # Control — each on its own cache line
    ("PCK1B",68,0,0,COL_C),("SDMRD",131,0,0,COL_S),("MROMOE",195,0,0,COL_M),
    # C-ROM data (orange)
    ("CR0",69,0,1,COL_C),("CR1",69,1,1,COL_C),("CR2",69,2,1,COL_C),("CR3",69,3,1,COL_C),
    ("CR4",69,4,1,COL_C),("CR5",69,5,1,COL_C),("CR6",69,6,1,COL_C),("CR7",69,7,1,COL_C),
    # S-ROM address (pink) — cache line 2
    ("SDA0",128,0,0,COL_S),("SDA1",128,1,0,COL_S),("SDA2",128,2,0,COL_S),("SDA3",128,3,0,COL_S),
    ("SDA4",128,4,0,COL_S),("SDA5",128,5,0,COL_S),("SDA6",128,6,0,COL_S),("SDA7",128,7,0,COL_S),
    # S-ROM data (pink)
    ("SDD0",132,0,1,COL_S),("SDD1",132,1,1,COL_S),("SDD2",132,2,1,COL_S),("SDD3",132,3,1,COL_S),
    ("SDD4",132,4,1,COL_S),("SDD5",132,5,1,COL_S),("SDD6",132,6,1,COL_S),("SDD7",132,7,1,COL_S),
    # Acknowledge — each on its own cache line
    ("CDTACK",73,0,1,COL_C),("SDTACK",133,0,1,COL_S),("MDTACK",197,0,1,COL_M),
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
        self.btn_emu = tk.Button(ctrl, text="Start Emu", command=self._launch_emu,
                                  bg='#333', fg='white', state=tk.DISABLED, padx=8)
        self.btn_emu.pack(side=tk.LEFT, padx=4)

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

        sep2 = tk.Frame(ctrl, bg='#444', width=2)
        sep2.pack(side=tk.LEFT, fill=tk.Y, padx=8)

        self.skeleton_on = False
        self.btn_skeleton = tk.Button(ctrl, text="Skeleton", command=self._toggle_skeleton,
                                       bg='#333', fg='white', padx=8, state=tk.DISABLED)
        self.btn_skeleton.pack(side=tk.LEFT, padx=4)

        self.lbl_game = tk.Label(ctrl, text="No game loaded", bg='#1a1a1a',
                                 fg=COL_TEXT, font=('monospace', 10))
        self.lbl_game.pack(side=tk.RIGHT, padx=10)

        # Notebook with two tabs: Pins and PCB
        from tkinter import ttk
        style = ttk.Style()
        style.configure('Dark.TNotebook', background=COL_BG)
        style.configure('Dark.TNotebook.Tab', background='#222', foreground='#aaa',
                         padding=[10,4])
        style.map('Dark.TNotebook.Tab', background=[('selected','#333')])

        notebook = ttk.Notebook(self.root, style='Dark.TNotebook')
        notebook.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        # Tab 1: Pin array view
        pin_tab = tk.Frame(notebook, bg=COL_BG)
        notebook.add(pin_tab, text='  Pins  ')

        self.prog_frame = tk.LabelFrame(pin_tab, text=" PROG (CTRG2) — P-ROM + V-ROM ",
                                         bg=COL_PCB, fg='#5a5', font=('monospace', 10, 'bold'),
                                         padx=6, pady=4)
        self.prog_frame.pack(fill=tk.X, pady=2)
        self.prog_pin_widgets = self._build_pin_row(self.prog_frame, PROG_PINS)

        self.cha_frame = tk.LabelFrame(pin_tab, text=" CHA (CTRG1) — C-ROM + S-ROM + M-ROM ",
                                        bg=COL_PCB, fg='#5a5', font=('monospace', 10, 'bold'),
                                        padx=6, pady=4)
        self.cha_frame.pack(fill=tk.X, pady=2)
        self.cha_pin_widgets = self._build_pin_row(self.cha_frame, CHA_PINS)

        # Tab 2: PCB view
        self.pcb_tab = tk.Frame(notebook, bg=COL_BG)
        notebook.add(self.pcb_tab, text='  PCB  ')
        self._build_pcb_view(self.pcb_tab)

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


    def _build_pcb_view(self, parent):
        self.pcb_canvases = []
        self.pcb_ic_items = []

        grid = tk.Frame(parent, bg=COL_BG)
        grid.pack(fill=tk.BOTH, expand=True)
        grid.grid_columnconfigure(0, weight=1)
        grid.grid_columnconfigure(1, weight=1)
        grid.grid_rowconfigure(0, weight=1)
        grid.grid_rowconfigure(1, weight=1)

        # Determine ROM IC layout from .neo header
        p_chips, v_chips, c_chips, s_chips, m_chips = [], [], [], [], []
        if self.neo_path:
            import struct
            with open(self.neo_path, 'rb') as f:
                hdr = f.read(256)
                ps = struct.unpack_from('<I', hdr, 4)[0]
                ss = struct.unpack_from('<I', hdr, 8)[0]
                ms = struct.unpack_from('<I', hdr, 12)[0]
                vs = struct.unpack_from('<I', hdr, 16)[0]
                cs = struct.unpack_from('<I', hdr, 24)[0]
            if ps > 0x100000:
                p_chips = [("P1","1MB",COL_P,0,0x100000), ("P2",f"{(ps-0x100000)//1024//1024}MB",COL_P,0x100000,ps)]
            else:
                p_chips = [("P1",f"{ps//1024}KB",COL_P,0,ps)]
            if vs > 0:
                vn = max(1, (vs + 0x3FFFFF) // 0x400000)
                for i in range(vn):
                    base = i * 0x400000
                    sz = min(0x400000, vs - base)
                    v_chips.append((f"V{i+1}",f"{sz//1024//1024}MB",COL_V,base,base+sz))
            cn = 0
            if cs > 0:
                pair_size = 0
                if cs <= 0x400000: pair_size = cs // 2
                elif cs <= 0x1000000: pair_size = 0x400000
                else: pair_size = 0x800000
                cn = max(2, (cs + pair_size - 1) // pair_size)
                if cn % 2: cn += 1
                for i in range(cn):
                    base = i * pair_size
                    c_chips.append((f"C{i+1}",f"{pair_size//1024//1024}MB",COL_C,base,base+pair_size))
            if ss > 0:
                s_chips = [("S1",f"{ss//1024}KB",COL_S,0,ss)]
            if ms > 0:
                m_chips = [("M1",f"{ms//1024}KB",COL_M,0,ms)]

        # Board proportions: 174mm x 134mm ≈ 1.3:1
        bw, bh = 480, 370
        finger_h = 24
        pcb_y1 = 8
        pcb_y2 = bh - finger_h - 8

        # Pin definitions per board side
        def make_60(entries):
            pins = []
            for i in range(60):
                found = False
                for num, name, color in entries:
                    if num == i+1:
                        pins.append((name, color))
                        found = True
                        break
                if not found:
                    pins.append(("NC", None))
            return pins

        prog_a_entries = [(i,"VCC","VCC") for i in range(1,5)] + \
            [(5+i,f"D{i}",COL_P) for i in range(16)] + \
            [(21,"nRW",COL_P),(22,"GND","GND"),(23,"ROMOEU",COL_P),(24,"ROMOEL",COL_P),
             (25,"GND","GND"),(33,"ROMOE",COL_P),(59,"+5V","VCC"),(60,"+5V","VCC")]

        prog_b_entries = [(i,"VCC","VCC") for i in range(1,5)] + \
            [(5+i,f"A{i+1}",COL_P) for i in range(19)] + \
            [(58,"GND","GND"),(59,"+5V","VCC"),(60,"+5V","VCC")]

        cha_a_entries = [(i,"VCC","VCC") for i in range(1,5)] + \
            [(5+i,f"P{i}",COL_C) for i in range(24)] + \
            [(29+i,f"CR{i}",COL_C) for i in range(8)] + \
            [(37,"PCK1B",COL_C),(38,"PCK2B",COL_C),(58,"GND","GND"),(59,"+5V","VCC"),(60,"+5V","VCC")]

        cha_b_entries = [(i,"VCC","VCC") for i in range(1,5)] + \
            [(5+i,f"SDA{i}",COL_S) for i in range(16)] + \
            [(21+i,f"SDD{i}",COL_S) for i in range(8)] + \
            [(29,"SDMRD",COL_S),(30,"PCK1B",COL_C),(31,"PCK2B",COL_C),(32,"GND","GND")] + \
            [(40+i,f"MA{i}",COL_M) for i in range(8)] + \
            [(48+i,f"MD{i}",COL_M) for i in range(8)] + \
            [(56,"MROMOE",COL_M),(58,"GND","GND"),(59,"+5V","VCC"),(60,"+5V","VCC")]

        boards = [
            ("PROG Front", make_60(prog_a_entries), p_chips + v_chips, 0, 0),
            ("PROG Back",  make_60(prog_b_entries), p_chips + v_chips, 0, 1),
            ("CHA Front",  make_60(cha_a_entries),  c_chips[:len(c_chips)//2], 1, 0),
            ("CHA Back",   make_60(cha_b_entries),  c_chips[len(c_chips)//2:] + s_chips + m_chips, 1, 1),
        ]

        for title, pins, ics, r, c in boards:
            f = tk.LabelFrame(grid, text=f" {title} ", bg='#0a0a0a', fg='#5a5',
                              font=('monospace', 9, 'bold'))
            f.grid(row=r, column=c, padx=3, pady=3, sticky='nsew')

            cv = tk.Canvas(f, width=bw, height=bh, bg='#0a0a0a', highlightthickness=0)
            cv.pack(padx=2, pady=2)

            # PCB body with rounded corners
            cv.create_rectangle(8, pcb_y1, bw-8, pcb_y2, fill='#1a4a1a', outline='#2a6a2a', width=2)

            # Mounting holes
            for hx, hy in [(30, 30), (bw-30, 30), (30, pcb_y2-22), (bw-30, pcb_y2-22)]:
                cv.create_oval(hx-6, hy-6, hx+6, hy+6, fill='#0a0a0a', outline='#2a6a2a')

            # Board title
            cv.create_text(bw//2, pcb_y1+16, text=title, fill='#2a5a2a', font=('monospace', 9, 'bold'))

            # IC packages
            ic_items = []
            if ics:
                cols = min(4, len(ics))
                rows_ic = (len(ics) + cols - 1) // cols
                ic_w = min(90, (bw - 80) // cols)
                ic_h = min(50, (pcb_y2 - 80) // rows_ic - 10)
                for idx, (ic_name, ic_size, ic_color, ic_base, ic_end) in enumerate(ics):
                    row_ic = idx // cols
                    col_ic = idx % cols
                    x0 = 50 + col_ic * (ic_w + 12)
                    y0 = 50 + row_ic * (ic_h + 14)
                    body = cv.create_rectangle(x0, y0, x0+ic_w, y0+ic_h,
                                               fill='#111', outline='#333', width=1)
                    # Pin notch
                    cv.create_oval(x0+4, y0+ic_h//2-3, x0+10, y0+ic_h//2+3,
                                   fill='#1a1a1a', outline='#333')
                    # IC pins (tiny ticks on sides)
                    pin_count = min(16, ic_h // 4)
                    for p in range(pin_count):
                        py = y0 + 4 + p * (ic_h - 8) // max(1, pin_count-1)
                        cv.create_line(x0-4, py, x0, py, fill='#666')
                        cv.create_line(x0+ic_w, py, x0+ic_w+4, py, fill='#666')
                    # Label
                    cv.create_text(x0+ic_w//2, y0+ic_h//2-6, text=ic_name,
                                   fill=ic_color, font=('monospace', 9, 'bold'))
                    cv.create_text(x0+ic_w//2, y0+ic_h//2+8, text=ic_size,
                                   fill='#555', font=('monospace', 7))
                    ic_items.append((body, ic_name, ic_color, ic_base, ic_end))

            # Notch at edge connector
            cv.create_arc(bw//2-10, pcb_y2-6, bw//2+10, pcb_y2+6, start=0, extent=180,
                          fill='#0a0a0a', outline='#2a6a2a')

            # Gold fingers
            pin_items = []
            pw = 6
            gap = 1
            total_w = 60 * (pw + gap)
            x_start = (bw - total_w) // 2
            for i, (name, color) in enumerate(pins):
                x = x_start + i * (pw + gap)
                y = pcb_y2
                if color == "VCC":
                    fill = '#661111'
                elif color == "GND":
                    fill = '#111111'
                elif color is None:
                    fill = '#aa8800'
                else:
                    fill = '#554400'
                rect = cv.create_rectangle(x, y, x+pw, y+finger_h, fill=fill, outline='')
                # Pin label
                lbl_color = '#dd2222' if color == "VCC" else '#333' if color == "GND" else '#555'
                cv.create_text(x+pw//2, y-5, text=name, fill=lbl_color,
                               font=('monospace', 4), angle=90)
                pin_items.append((rect, name, color))

            self.pcb_canvases.append((cv, pin_items))
            self.pcb_ic_items.append((cv, ic_items))

    def _update_pcb_pins(self):
        if not self.raw:
            return
        sig_state = {}
        for pins in [PROG_PINS, CHA_PINS]:
            for name, byte_off, bit, is_out, col_hi in pins:
                if byte_off < SHM_SIZE:
                    sig_state[name] = (self.raw[byte_off] >> bit) & 1

        for cv, pin_items in self.pcb_canvases:
            for rect, name, color in pin_items:
                if color in (None, "VCC", "GND"):
                    continue
                active = sig_state.get(name, 0)
                cv.itemconfig(rect, fill=color if active else '#332200')

        # Light up active ICs
        romoe = not (self.raw[3] & 0x01) if self.raw else False
        vromoe = not (self.raw[323] & 0x01) if self.raw else False
        pck1b = not (self.raw[68] & 0x01) if self.raw else False
        sromoe = not (self.raw[131] & 0x01) if self.raw else False
        mromoe = not (self.raw[195] & 0x01) if self.raw else False

        paddr = (self.raw[0] | (self.raw[1]<<8) | ((self.raw[2]&0x07)<<16)) if self.raw else 0
        caddr = (self.raw[64] | (self.raw[65]<<8) | (self.raw[66]<<16) | (self.raw[67]<<24)) if self.raw else 0
        saddr = (self.raw[128] | (self.raw[129]<<8) | (self.raw[130]<<16)) if self.raw else 0

        for cv, ic_items in self.pcb_ic_items:
            for body, ic_name, ic_color, ic_base, ic_end in ic_items:
                active = False
                if ic_name.startswith('P') and romoe:
                    active = ic_base <= paddr < ic_end
                elif ic_name.startswith('V') and vromoe:
                    active = True
                elif ic_name.startswith('C') and pck1b:
                    active = ic_base <= caddr < ic_end
                elif ic_name.startswith('S') and sromoe:
                    active = True
                elif ic_name.startswith('M') and mromoe:
                    active = True
                cv.itemconfig(body, fill=ic_color if active else '#111',
                              outline=ic_color if active else '#333')

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
            self._update_pcb_pins()

            # P-ROM (line 0)
            paddr = self.raw[0] | (self.raw[1]<<8) | ((self.raw[2]&0x07)<<16)
            pdata = self.raw[4] | (self.raw[5]<<8)
            romoe = not (self.raw[3] & 0x01)
            pdtack = not (self.raw[6] & 0x01)
            if romoe or pdtack:
                self.rom_labels["P-ROM"].config(text=f"P-ROM  ADDR 0x{paddr:06X}  DATA 0x{pdata:04X}  /OE {'*' if romoe else '-'}  /DTACK {'*' if pdtack else '-'}")
            else:
                self.rom_labels["P-ROM"].config(text=f"P-ROM  idle")

            # V-ROM (line 5)
            vaddr = self.raw[320] | (self.raw[321]<<8) | (self.raw[322]<<16)
            vdata = self.raw[324]
            vromoe = not (self.raw[323] & 0x01)
            vdtack = not (self.raw[325] & 0x01)
            if vromoe or vdtack:
                self.rom_labels["V-ROM"].config(text=f"V-ROM  ADDR 0x{vaddr:06X}  DATA 0x{vdata:02X}  /OE {'*' if vromoe else '-'}  /DTACK {'*' if vdtack else '-'}")
            else:
                self.rom_labels["V-ROM"].config(text=f"V-ROM  idle")

            # C-ROM (line 1)
            caddr = self.raw[64] | (self.raw[65]<<8) | (self.raw[66]<<16) | (self.raw[67]<<24)
            cdata = self.raw[69] | (self.raw[70]<<8)
            pck1b = not (self.raw[68] & 0x01)
            cdtack = not (self.raw[73] & 0x01)
            if pck1b or cdtack:
                self.rom_labels["C-ROM"].config(text=f"C-ROM  ADDR 0x{caddr:07X}  DATA 0x{cdata:04X}  /PCK1B {'*' if pck1b else '-'}  /DTACK {'*' if cdtack else '-'}")
            else:
                self.rom_labels["C-ROM"].config(text=f"C-ROM  idle")

            # S-ROM (line 2)
            saddr = self.raw[128] | (self.raw[129]<<8) | (self.raw[130]<<16)
            sdata = self.raw[132]
            sromoe = not (self.raw[131] & 0x01)
            sdtack = not (self.raw[133] & 0x01)
            if sromoe or sdtack:
                self.rom_labels["S-ROM"].config(text=f"S-ROM  ADDR 0x{saddr:05X}  DATA 0x{sdata:02X}  /SDMRD {'*' if sromoe else '-'}  /DTACK {'*' if sdtack else '-'}")
            else:
                self.rom_labels["S-ROM"].config(text=f"S-ROM  idle")

            # M-ROM (line 3)
            maddr = self.raw[192] | (self.raw[193]<<8) | ((self.raw[194]&1)<<16)
            mdata = self.raw[196]
            mromoe = not (self.raw[195] & 0x01)
            mdtack = not (self.raw[197] & 0x01)
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
            # Rebuild PCB view with new ROM layout
            for w in self.pcb_tab.winfo_children():
                w.destroy()
            self.pcb_canvases = []
            self.pcb_ic_items = []
            self._build_pcb_view(self.pcb_tab)

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
        self.btn_emu.config(state=tk.NORMAL)
        self.btn_pause.config(state=tk.NORMAL)
        self.btn_skeleton.config(state=tk.NORMAL)
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
        try:
            self.btn_start.config(state=tk.NORMAL)
            self.btn_stop.config(state=tk.DISABLED)
            self.btn_emu.config(state=tk.DISABLED)
            self.btn_skeleton.config(state=tk.DISABLED)
            self.lbl_status.config(text="Server: stopped")
        except tk.TclError:
            pass

    def _pause(self):
        if self.shm_rw:
            self.shm_rw[385] = 1
            self.paused = True
            self.btn_pause.config(state=tk.DISABLED)
            self.btn_step.config(state=tk.NORMAL)
            self.btn_resume.config(state=tk.NORMAL)
            self.lbl_status.config(text="Server: PAUSED")

    def _step(self):
        if self.shm_rw and self.paused:
            self.shm_rw[386] = 1

    def _resume(self):
        if self.shm_rw:
            self.shm_rw[385] = 0
            self.paused = False
            self.btn_pause.config(state=tk.NORMAL)
            self.btn_step.config(state=tk.DISABLED)
            self.btn_resume.config(state=tk.DISABLED)
            self.lbl_status.config(text=f"Server: running")

    def _toggle_skeleton(self):
        if self.shm_rw:
            self.skeleton_on = not self.skeleton_on
            self.shm_rw[384] = 1 if self.skeleton_on else 0
            self.btn_skeleton.config(
                bg='#aa3300' if self.skeleton_on else '#333',
                text='Skeleton ON' if self.skeleton_on else 'Skeleton')

    def _launch_emu(self):
        if not self.neo_path:
            return
        subprocess.Popen([
            NEOSCAN_EMU, self.neo_path
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

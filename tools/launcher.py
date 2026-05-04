#!/usr/bin/env python3
"""NeoScanSDK Launcher — shortcut buttons from shortcuts.json"""
import tkinter as tk
import subprocess, json, os

SHORTCUTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shortcuts.json")

class Launcher:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("NeoScanSDK")
        self.root.configure(bg='#0a0a0a')
        self.root.resizable(False, False)
        self.root.wm_iconname('neoscansdk')
        self.root.tk.call('tk', 'appname', 'neoscansdk')
        self._build()

    def _build(self):
        with open(SHORTCUTS) as f:
            shortcuts = json.load(f)

        tk.Label(self.root, text="NeoScanSDK", bg='#0a0a0a', fg='#00ff44',
                 font=('monospace', 14, 'bold'), pady=8).pack()

        for sc in shortcuts:
            btn = tk.Button(self.root, text=sc["label"],
                            command=lambda c=sc["cmd"]: self._run(c),
                            bg='#1a1a1a', fg='white', activebackground='#333',
                            activeforeground='#00ff44', font=('monospace', 11),
                            width=30, pady=4, relief=tk.FLAT, cursor='hand2')
            btn.pack(padx=12, pady=3)

        tk.Frame(self.root, bg='#0a0a0a', height=8).pack()

    def _run(self, cmd):
        expanded = os.path.expanduser(cmd)
        subprocess.Popen(expanded, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def run(self):
        self.root.mainloop()

if __name__ == '__main__':
    Launcher().run()

"""
PCB Engine — Programmatic PCB design library for AI-driven hardware design.

Usage:
    from pcb_engine import Board, Component, Package

    board = Board(100, 80, layers=2)
    r1 = board.place("R1", "R_0402", x=50, y=40)
    r2 = board.place("R2", "R_0402", x=60, y=40)
    board.net("SIG").connect(r1.pad(1), r2.pad(1))
    board.net("GND").connect(r1.pad(2), r2.pad(2))
    board.route()
    board.export_gerbers("output/")
"""

from pcb_engine.board import Board
from pcb_engine.component import Component, Package, Pad
from pcb_engine.router import Router
from pcb_engine.drc import DRC
from pcb_engine.exporter import GerberExporter, BOMExporter
from pcb_engine.renderer import Renderer

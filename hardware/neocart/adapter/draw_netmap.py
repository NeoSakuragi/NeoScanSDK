#!/usr/bin/env python3
"""Draw visual net diagrams for both adapter boards."""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as patches

def draw_board(ax, title, components, connections, board_w=174, board_h=134):
    ax.set_xlim(-10, board_w + 10)
    ax.set_ylim(board_h + 10, -10)
    ax.set_aspect('equal')
    ax.axis('off')
    ax.set_title(title, fontsize=14, fontweight='bold', family='monospace')

    # Board outline
    board = patches.FancyBboxPatch((0, 0), board_w, board_h, boxstyle="round,pad=1",
                                    linewidth=2, edgecolor='#333', facecolor='#e8f5e9')
    ax.add_patch(board)

    # Draw components as boxes
    comp_centers = {}
    for name, x, y, w, h, color, label in components:
        rect = patches.FancyBboxPatch((x - w/2, y - h/2), w, h, boxstyle="round,pad=0.3",
                                       linewidth=1.5, edgecolor=color, facecolor='white')
        ax.add_patch(rect)
        ax.text(x, y - 1, name, ha='center', va='center', fontsize=7, fontweight='bold',
                family='monospace', color=color)
        ax.text(x, y + 3, label, ha='center', va='center', fontsize=5,
                family='monospace', color='#666')
        comp_centers[name] = (x, y)

    # Draw connections
    for src, dst, net_label, color, style in connections:
        if src in comp_centers and dst in comp_centers:
            x1, y1 = comp_centers[src]
            x2, y2 = comp_centers[dst]
            ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
                        arrowprops=dict(arrowstyle='->', color=color, lw=1.2,
                                       connectionstyle=f'arc3,rad={style}'))
            mx, my = (x1+x2)/2, (y1+y2)/2
            ax.text(mx, my - 2, net_label, ha='center', va='center', fontsize=5,
                    color=color, family='monospace', fontstyle='italic',
                    bbox=dict(boxstyle='round,pad=0.1', facecolor='white', edgecolor='none', alpha=0.8))


# ════════════════════════════════════════
# PROG BOARD
# ════════════════════════════════════════
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(28, 16))

prog_components = [
    # name, x, y, w, h, color, label
    ('CTRG2', 87, 125, 150, 12, '#cc6600', 'Gold Fingers (60x2)\nPD0-15, PA0-17, VD0-7\nnRW, ROMOEU, ROMOEL, SDROE'),
    ('J1', 30, 40, 20, 70, '#0055aa', 'FPGA U2\n(PROG signals)\nFD0-15, VD0-7\nSER_P, CLK_P\nLOAD_P, SD_*'),
    ('J3', 91, 40, 20, 70, '#0055aa', 'FPGA U1\n(CHA signals)\nCR0-31, SDD0-7\nSER_C/S, CLK_C/S'),
    ('J2', 155, 40, 14, 70, '#9900cc', 'Inter-board\nTO CHA\nCR0-31\nSDD0-7\ncontrol'),
    ('U1', 55, 30, 16, 14, '#cc0000', '74LVC245\nPD0-7 <-> FD0-7'),
    ('U2', 55, 55, 16, 14, '#cc0000', '74LVC245\nPD8-15 <-> FD8-15'),
    ('U3', 55, 78, 12, 10, '#008800', '74HC165\nPA0-7 serial'),
    ('U4', 55, 92, 12, 10, '#008800', '74HC165\nPA8-15 serial'),
    ('U5', 55, 106, 12, 10, '#008800', '74HC165\nPA16-17+ctrl'),
    ('R1-22', 120, 95, 20, 8, '#888', '22x 470R\nMVS->SR'),
    ('J4', 60, 10, 16, 10, '#006666', 'microSD\nSPI mode'),
]

prog_connections = [
    # src, dst, label, color, arc_rad
    ('CTRG2', 'U1', 'PD0-7 (5V)', '#cc6600', 0.15),
    ('CTRG2', 'U2', 'PD8-15 (5V)', '#cc6600', 0.1),
    ('U1', 'J1', 'FD0-7 (3.3V)', '#0055aa', -0.15),
    ('U2', 'J1', 'FD8-15 (3.3V)', '#0055aa', -0.1),
    ('CTRG2', 'R1-22', 'PA0-17, ctrl (5V)', '#cc6600', -0.2),
    ('R1-22', 'U3', 'PA0-7 (protected)', '#008800', 0.15),
    ('R1-22', 'U4', 'PA8-15', '#008800', 0.1),
    ('R1-22', 'U5', 'PA16-17+ctrl', '#008800', 0.05),
    ('U3', 'U4', 'SR1_OUT (chain)', '#008800', 0.0),
    ('U4', 'U5', 'SR2_OUT (chain)', '#008800', 0.0),
    ('U5', 'J1', 'SER_P (serial)', '#0055aa', 0.2),
    ('J1', 'CTRG2', 'VD0-7 (direct)', '#0055aa', 0.3),
    ('J1', 'J4', 'SD SPI (4 lines)', '#006666', 0.0),
    ('J3', 'J2', 'CR0-31, SDD0-7\nCHA control\n(passthrough)', '#9900cc', 0.0),
    ('J1', 'U1', 'BUS_DIR, BUF_OE', '#cc0000', 0.1),
    ('J1', 'U3', 'CLK_P, LOAD_P', '#008800', 0.2),
    ('CTRG2', 'J1', 'ROMOE, SDROE', '#cc6600', -0.35),
]

draw_board(ax1, 'NEOCART PROG — Net Map', prog_components, prog_connections)

# ════════════════════════════════════════
# CHA BOARD
# ════════════════════════════════════════

cha_components = [
    ('CTRG1', 87, 125, 150, 12, '#cc6600', 'Gold Fingers (60x2)\nCR0-31 (out), SDD0-7 (out)\nCA0-23, SA0-15 (in), PCK1B/2B, SDMRD'),
    ('J2', 20, 50, 14, 70, '#9900cc', 'Inter-board\nFROM PROG\nCR0-31\nSDD0-7\ncontrol'),
    ('U1', 55, 35, 12, 10, '#008800', '74HC165\nCA0-7 serial'),
    ('U2', 55, 52, 12, 10, '#008800', '74HC165\nCA8-15 serial'),
    ('U3', 55, 69, 12, 10, '#008800', '74HC165\nCA16-23 serial'),
    ('U4', 120, 35, 12, 10, '#008800', '74HC165\nSA0-7 serial'),
    ('U5', 120, 52, 12, 10, '#008800', '74HC165\nSA8-15 serial'),
    ('R1-24', 80, 52, 16, 8, '#888', '24x 470R\nC-ROM addr'),
    ('R25-40', 145, 45, 16, 8, '#888', '16x 470R\nS-ROM addr'),
]

cha_connections = [
    ('J2', 'CTRG1', 'CR0-31 (direct out)', '#0055aa', -0.25),
    ('J2', 'CTRG1', 'SDD0-7 (direct out)', '#0055aa', -0.15),
    ('CTRG1', 'R1-24', 'CA0-23 (5V in)', '#cc6600', 0.15),
    ('CTRG1', 'R25-40', 'SA0-15 (5V in)', '#cc6600', -0.15),
    ('R1-24', 'U1', 'CA0-7 (protected)', '#008800', 0.1),
    ('R1-24', 'U2', 'CA8-15', '#008800', 0.0),
    ('R1-24', 'U3', 'CA16-23', '#008800', -0.1),
    ('R25-40', 'U4', 'SA0-7 (protected)', '#008800', 0.1),
    ('R25-40', 'U5', 'SA8-15', '#008800', -0.1),
    ('U1', 'U2', 'SR1C_OUT', '#008800', 0.0),
    ('U2', 'U3', 'SR2C_OUT', '#008800', 0.0),
    ('U3', 'J2', 'SER_C (serial)', '#9900cc', 0.2),
    ('U4', 'U5', 'SR1S_OUT', '#008800', 0.0),
    ('U5', 'J2', 'SER_S (serial)', '#9900cc', -0.2),
    ('J2', 'U1', 'CLK_C, LOAD_C', '#008800', 0.15),
    ('J2', 'U4', 'CLK_S, LOAD_S', '#008800', -0.1),
    ('CTRG1', 'J2', 'PCK1B, PCK2B, SDMRD', '#cc6600', 0.3),
]

draw_board(ax2, 'NEOCART CHA-256 — Net Map', cha_components, cha_connections)

plt.tight_layout()
out = '/home/bruno/CLProjects/NeoScanSDK/hardware/neocart/adapter/netmap.png'
fig.savefig(out, dpi=150, bbox_inches='tight')
print(f"Saved: {out}")

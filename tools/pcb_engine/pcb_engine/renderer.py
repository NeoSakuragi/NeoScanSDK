"""
Renderer — produces PNG images of the board.
Color scheme inspired by real PCBs:
  Board: dark green
  F.Cu traces: red
  B.Cu traces: blue
  Pads: gold/yellow
  Silkscreen: white
  Board edge: yellow
  Via: green circle
"""

from PIL import Image, ImageDraw, ImageFont
import math


class Renderer:
    COLORS = {
        "board": (30, 60, 30),
        "F.Cu": (200, 40, 40),
        "B.Cu": (40, 40, 200),
        "pad": (220, 200, 50),
        "via": (50, 200, 50),
        "edge": (200, 200, 50),
        "silk": (220, 220, 220),
        "ratsnest": (100, 200, 200, 80),
        "background": (40, 40, 50),
    }

    def __init__(self, board):
        self.board = board

    def render(self, path: str, dpi: int = 300, side: str = "top",
              margin_mm: float = 5, show_ratsnest: bool = True):
        b = self.board
        scale = dpi / 25.4  # pixels per mm

        img_w = int((b.width + 2 * margin_mm) * scale)
        img_h = int((b.height + 2 * margin_mm) * scale)

        img = Image.new("RGB", (img_w, img_h), self.COLORS["background"])
        draw = ImageDraw.Draw(img, "RGBA")

        def mm2px(x, y):
            return (int((x + margin_mm) * scale), int((y + margin_mm) * scale))

        # Board outline
        if b.outline:
            pts = [mm2px(x, y) for x, y in b.outline]
            pts.append(pts[0])
            draw.polygon(pts, fill=self.COLORS["board"])
            for i in range(len(pts) - 1):
                draw.line([pts[i], pts[i+1]], fill=self.COLORS["edge"], width=max(1, int(0.3*scale)))

        # Zones (faint fill)
        for zone in b.zones:
            if zone.outline:
                pts = [mm2px(x, y) for x, y in zone.outline]
                color = self.COLORS.get(zone.layer, (50, 50, 50))
                faint = (color[0]//3, color[1]//3, color[2]//3, 40)
                draw.polygon(pts, fill=faint)

        # Traces
        for t in b.traces:
            if side == "top" and t.layer == "B.Cu":
                continue
            if side == "bottom" and t.layer == "F.Cu":
                continue
            color = self.COLORS.get(t.layer, (150, 150, 150))
            p1 = mm2px(t.x1, t.y1)
            p2 = mm2px(t.x2, t.y2)
            width = max(1, int(t.width * scale))
            draw.line([p1, p2], fill=color, width=width)

        # Vias
        for v in b.vias:
            cx, cy = mm2px(v.x, v.y)
            r = max(2, int(v.diameter / 2 * scale))
            draw.ellipse([cx-r, cy-r, cx+r, cy+r], fill=self.COLORS["via"],
                        outline=(200, 200, 200))

        # Components
        for comp in b.components.values():
            pkg = comp.package
            half_w = pkg.width / 2
            half_h = pkg.height / 2

            # Component body
            corners = [(-half_w, -half_h), (half_w, -half_h),
                      (half_w, half_h), (-half_w, half_h)]
            rad = math.radians(comp.angle)
            rotated = []
            for cx, cy in corners:
                rx = cx * math.cos(rad) - cy * math.sin(rad)
                ry = cx * math.sin(rad) + cy * math.cos(rad)
                rotated.append(mm2px(comp.x + rx, comp.y + ry))
            draw.polygon(rotated, fill=(50, 50, 50), outline=(120, 120, 120))

            # Pads
            for pad_num, ax, ay, net in comp.all_pads_abs():
                px, py = mm2px(ax, ay)
                p = comp.pad(pad_num)
                pw = max(2, int(p.width * scale / 2))
                ph = max(2, int(p.height * scale / 2))
                draw.rectangle([px-pw, py-ph, px+pw, py+ph], fill=self.COLORS["pad"])

            # Reference label
            lx, ly = mm2px(comp.x, comp.y - pkg.height/2 - 1.5)
            try:
                draw.text((lx, ly), comp.ref, fill=self.COLORS["silk"], anchor="mm")
            except:
                draw.text((lx-10, ly-5), comp.ref, fill=self.COLORS["silk"])

        # Ratsnest (unrouted connections)
        if show_ratsnest:
            routed_nets = {t.net for t in b.traces}
            for net_name, net in b.nets.items():
                if net_name in routed_nets:
                    continue
                pads = b.get_net_pads(net_name)
                for i in range(len(pads) - 1):
                    p1 = mm2px(pads[i][0], pads[i][1])
                    p2 = mm2px(pads[i+1][0], pads[i+1][1])
                    draw.line([p1, p2], fill=self.COLORS["ratsnest"], width=1)

        img.save(path)
        return path

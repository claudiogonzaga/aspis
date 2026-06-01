#!/usr/bin/env python3
"""Ícone do Clípeo: um Gorgoneion (a face frontal da Medusa, com serpentes no
lugar dos cabelos) gravado no disco de bronze de um escudo redondo (aspis) —
o motivo apotropaico clássico e a "cara" do escudo de Perseu.

Saída: assets/clipeo_icon_1024.png. build_icns.sh gera o .icns.

Abordagem: disco metálico (numpy, gradiente radial). O Gorgoneion é desenhado
como BAIXO-RELEVO no próprio bronze: traços claros (luz) e escuros (sombra)
sobre o tom do disco, em vez de cores chapadas — assim parece cunhado no metal.
Supersampling 2x + LANCZOS.
"""
import math
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

OUT = 1024
W = OUT * 2
C = W / 2.0


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


# ---------- fundo squircle escuro ----------
ax = (np.arange(W) + 0.5) / W * 2 - 1
xx, yy = np.meshgrid(ax, ax)
se = (np.abs(xx / 0.94) ** 5.0 + np.abs(yy / 0.94) ** 5.0)
bg_alpha = smoothstep(1.012, 0.988, se)
g = (yy + 1) / 2
bg = (np.array([0.115, 0.142, 0.212])[None, None, :] * (1 - g[..., None])
      + np.array([0.035, 0.047, 0.082])[None, None, :] * g[..., None])
glow = np.clip(1 - np.sqrt((xx + 0.4) ** 2 + (yy + 0.4) ** 2) / 1.4, 0, 1) ** 2
bg = np.clip(bg + glow[..., None] * np.array([0.05, 0.06, 0.09])[None, None, :], 0, 1)

# ---------- disco de bronze ----------
R = 0.72
dist = np.sqrt(xx ** 2 + yy ** 2)
rr = dist / R
dome = np.sqrt(np.clip(1 - np.clip(rr, 0, 1) ** 2, 0, 1))
diag = (-(xx) - (yy)) / 1.5
lum = np.clip(0.36 + 0.46 * (dome * 0.9 + 0.1) + 0.16 * diag, 0, 1)
ringband = np.exp(-((rr - 0.9) ** 2) / (2 * 0.02 ** 2))
lum = np.clip(lum - 0.16 * ringband, 0, 1)

stops = np.array([0.00, 0.30, 0.55, 0.75, 0.90, 1.00])
pal_r = np.array([0x3a, 0x73, 0xad, 0xd9, 0xef, 0xff]) / 255
pal_g = np.array([0x25, 0x49, 0x76, 0xa2, 0xc9, 0xf6]) / 255
pal_b = np.array([0x10, 0x1b, 0x2b, 0x40, 0x66, 0xda]) / 255
bronze = np.stack([np.interp(lum, stops, pal_r),
                   np.interp(lum, stops, pal_g),
                   np.interp(lum, stops, pal_b)], axis=-1)
rim = smoothstep(0.965, 0.995, rr) * smoothstep(1.02, 0.995, rr)
bronze = bronze * (1 - 0.55 * rim[..., None])
disc_alpha = smoothstep(1.004, 0.996, rr)

sh = smoothstep(1.16, 0.7, np.sqrt((xx - 0.04) ** 2 + (yy - 0.05) ** 2) / R) * 0.5
img = bg * (1 - sh[..., None] * 0.9)
a = disc_alpha[..., None]
img = np.clip(img * (1 - a) + bronze * a, 0, 1)
base = Image.fromarray((np.dstack([img, bg_alpha]) * 255 + 0.5).astype(np.uint8))
base = base.convert("RGBA")

# tom médio do bronze (para o relevo se fundir ao disco)
MID = (181, 140, 70)
LO = (96, 70, 30)      # sombra gravada
LO2 = (60, 43, 18)     # sombra profunda (contorno)
HI = (245, 224, 150)   # realce (luz no metal)


def P(cx, cy, r):
    return [cx - r, cy - r, cx + r, cy + r]


def draw_gorgon(d, ink_lo, ink_lo2, ink_hi, mid, dy=0.0):
    """Desenha o relevo. dy desloca verticalmente (usado p/ camada de sombra)."""
    face_r = R * C * 0.46
    cy = C + dy

    # --- serpentes: laços curtos e grossos radiando, em pares (cabelo de cobras) ---
    n = 10
    ring_r = face_r * 1.02
    for i in range(n):
        ang = (i / n) * 2 * math.pi - math.pi / 2
        bx, by = C + math.cos(ang) * ring_r, cy + math.sin(ang) * ring_r
        seglen = face_r * 0.62
        nb = 5
        pts = []
        for j in range(nb):
            t = j / (nb - 1)
            perp = ang + math.pi / 2
            wob = math.sin(t * math.pi * 1.6 + i * 1.3) * face_r * 0.22
            px = bx + math.cos(ang) * seglen * t + math.cos(perp) * wob
            py = by + math.sin(ang) * seglen * t + math.sin(perp) * wob
            pts.append((px, py, face_r * (0.20 * (1 - 0.45 * t))))
        # corpo: sombra grossa + preenchimento médio + fio de luz
        for px, py, rad in pts:
            d.ellipse(P(px, py, rad + face_r * 0.05), fill=ink_lo2)
        for px, py, rad in pts:
            d.ellipse(P(px, py, rad), fill=mid)
        for px, py, rad in pts:
            d.ellipse(P(px - rad * 0.35, py - rad * 0.35, rad * 0.42), fill=ink_hi)
        # cabeça
        hx, hy, _ = pts[-1]
        hx += math.cos(ang) * face_r * 0.12
        hy += math.sin(ang) * face_r * 0.12
        d.ellipse(P(hx, hy, face_r * 0.13 + face_r * 0.04), fill=ink_lo2)
        d.ellipse(P(hx, hy, face_r * 0.13), fill=mid)

    # --- rosto ---
    d.ellipse(P(C, cy, face_r + face_r * 0.05), fill=ink_lo2)
    d.ellipse(P(C, cy, face_r), fill=mid)
    # bochechas com leve sombreado nas laterais
    d.ellipse(P(C, cy, face_r * 0.98), outline=ink_lo, width=int(face_r * 0.04))

    # --- olhos amendoados, grandes, severos ---
    eye_dx, eye_dy, ew, eh = face_r * 0.40, -face_r * 0.06, face_r * 0.30, face_r * 0.20
    for sgn in (-1, 1):
        ex, ey = C + sgn * eye_dx, cy + eye_dy
        d.ellipse([ex - ew, ey - eh, ex + ew, ey + eh], fill=ink_lo2)              # órbita
        d.ellipse([ex - ew * 0.86, ey - eh * 0.82, ex + ew * 0.86, ey + eh * 0.82],
                  fill=ink_hi)                                                      # esclera clara
        d.ellipse(P(ex, ey, eh * 0.62), fill=ink_lo2)                              # íris
        d.ellipse(P(ex, ey, eh * 0.30), fill=(15, 12, 8))                          # pupila
    # sobrancelhas grossas franzidas (V) — fúria
    bw = int(face_r * 0.10)
    d.line([C - eye_dx - ew, cy + eye_dy - eh * 1.25,
            C - face_r * 0.06, cy + eye_dy - eh * 0.45], fill=ink_lo2, width=bw)
    d.line([C + eye_dx + ew, cy + eye_dy - eh * 1.25,
            C + face_r * 0.06, cy + eye_dy - eh * 0.45], fill=ink_lo2, width=bw)

    # --- nariz ---
    ny = cy + face_r * 0.30
    d.line([C, cy + eye_dy + eh * 0.2, C, ny], fill=ink_lo, width=int(face_r * 0.05))
    d.ellipse(P(C - face_r * 0.05, ny, face_r * 0.045), fill=ink_lo2)
    d.ellipse(P(C + face_r * 0.05, ny, face_r * 0.045), fill=ink_lo2)

    # --- boca aberta + dentes + língua (traço icônico do Gorgoneion) ---
    my, mw = cy + face_r * 0.58, face_r * 0.40
    d.ellipse([C - mw, my - face_r * 0.14, C + mw, my + face_r * 0.16], fill=(20, 12, 8))
    d.rectangle([C - mw * 0.82, my - face_r * 0.12, C + mw * 0.82, my - face_r * 0.03],
                fill=ink_hi)  # dentes
    # divisórias dos dentes
    for t in (-0.5, 0, 0.5):
        xx0 = C + t * mw * 1.3
        d.line([xx0, my - face_r * 0.12, xx0, my - face_r * 0.03], fill=(120, 90, 50),
               width=max(2, int(face_r * 0.012)))
    d.ellipse([C - face_r * 0.13, my + face_r * 0.0, C + face_r * 0.13, my + face_r * 0.30],
              fill=(150, 55, 48))  # língua


# camada de sombra (deslocada) + camada principal, depois blur leve
shadow = Image.new("RGBA", (W, W), (0, 0, 0, 0))
draw_gorgon(ImageDraw.Draw(shadow), (0, 0, 0, 150), (0, 0, 0, 180),
            (0, 0, 0, 120), (0, 0, 0, 120), dy=W * 0.006)
shadow = shadow.filter(ImageFilter.GaussianBlur(W / 200))

layer = Image.new("RGBA", (W, W), (0, 0, 0, 0))
draw_gorgon(ImageDraw.Draw(layer), LO + (255,), LO2 + (255,), HI + (255,), MID + (255,))

out = Image.alpha_composite(base, shadow)
out = Image.alpha_composite(out, layer)

icon = out.resize((OUT, OUT), Image.LANCZOS)
path = os.path.join(os.path.dirname(__file__) or ".", "clipeo_icon_1024.png")
icon.save(path)
print("salvo:", path, icon.size)

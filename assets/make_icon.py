#!/usr/bin/env python3
"""Ícone do Aspis: um Gorgoneion (face frontal da Medusa, serpentes no lugar
dos cabelos) no estilo da cerâmica grega de figuras negras (black-figure):
silhueta PRETA sobre fundo TERRACOTA, com detalhes "incisos" em terracota.
É o motivo apotropaico clássico do escudo de Perseu, no idioma visual dos vasos
e escudos (aspis) gregos.

Saída: assets/aspis_icon_1024.png. build_icns.sh gera o .icns.
Supersampling 2x + LANCZOS.
"""
import math
import os

import numpy as np
from PIL import Image, ImageDraw

OUT = 1024
W = OUT * 2
C = W / 2.0

# paleta cerâmica grega
TERRA = (198, 92, 42)        # terracota (fundo do disco)
TERRA_HI = (216, 120, 66)    # terracota clara (brilho)
TERRA_LO = (150, 64, 30)     # terracota escura (sombra/anel)
BLACK = (24, 18, 16)         # verniz negro (a figura)
NIGHT = (20, 22, 30)         # fundo do squircle


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


# ============ fundo squircle escuro + disco terracota (numpy) ============
ax = (np.arange(W) + 0.5) / W * 2 - 1
xx, yy = np.meshgrid(ax, ax)
se = (np.abs(xx / 0.94) ** 5.0 + np.abs(yy / 0.94) ** 5.0)
bg_alpha = smoothstep(1.012, 0.988, se)

g = (yy + 1) / 2
night = (np.array([0.10, 0.11, 0.15])[None, None, :] * (1 - g[..., None])
         + np.array([0.04, 0.045, 0.07])[None, None, :] * g[..., None])

R = 0.72
rr = np.sqrt(xx ** 2 + yy ** 2) / R
# leve abaulamento + iluminação alto-esquerda para o disco de cerâmica
dome = np.sqrt(np.clip(1 - np.clip(rr, 0, 1) ** 2, 0, 1))
shade = np.clip(0.82 + 0.28 * dome + 0.12 * ((-(xx) - (yy)) / 1.5), 0.45, 1.18)

terra = np.array(TERRA) / 255.0
disc = np.clip(terra[None, None, :] * shade[..., None], 0, 1)

# anéis pretos concêntricos perto da borda (típicos da cerâmica)
band = np.zeros_like(rr)
for rc, wd in ((0.995, 0.02), (0.90, 0.016)):
    band += np.exp(-((rr - rc) ** 2) / (2 * wd ** 2))
band = np.clip(band, 0, 1)
blk = np.array(BLACK) / 255.0
disc = disc * (1 - band[..., None]) + blk[None, None, :] * band[..., None]

disc_alpha = smoothstep(1.004, 0.996, rr)
sh = smoothstep(1.16, 0.7, np.sqrt((xx - 0.04) ** 2 + (yy - 0.05) ** 2) / R) * 0.5
img = night * (1 - sh[..., None] * 0.9)
aa = disc_alpha[..., None]
img = np.clip(img * (1 - aa) + disc * aa, 0, 1)
base = Image.fromarray((np.dstack([img, bg_alpha]) * 255 + 0.5).astype(np.uint8)).convert("RGBA")

# ============ Gorgoneion em figura negra (ImageDraw, vetorial) ============
fig = Image.new("RGBA", (W, W), (0, 0, 0, 0))
d = ImageDraw.Draw(fig)
TR = (*TERRA, 255)
TRl = (*TERRA_LO, 255)
BK = (*BLACK, 255)


def P(cx, cy, r):
    return [cx - r, cy - r, cx + r, cy + r]


face_r = R * C * 0.42


def snake(ang, length, width0, wob_amp, wob_freq, phase):
    """Desenha uma serpente preta como polilínea grossa (corpo) com a cabeça."""
    n = 26
    pts = []
    for j in range(n):
        t = j / (n - 1)
        perp = ang + math.pi / 2
        wob = math.sin(t * math.pi * wob_freq + phase) * wob_amp * (0.4 + 0.6 * t)
        px = C + math.cos(ang) * (face_r * 0.92 + length * t) + math.cos(perp) * wob
        py = C + math.sin(ang) * (face_r * 0.92 + length * t) + math.sin(perp) * wob
        pts.append((px, py))
    # corpo afinando: desenha como sequência de segmentos com largura decrescente
    for j in range(len(pts) - 1):
        t = j / (len(pts) - 1)
        wd = max(2, width0 * (1 - 0.55 * t))
        d.line([pts[j], pts[j + 1]], fill=BK, width=int(wd))
        d.ellipse(P(pts[j][0], pts[j][1], wd / 2), fill=BK)
    # cabeça triangular (boca aberta da cobra)
    hx, hy = pts[-1]
    hr = width0 * 0.62
    d.ellipse(P(hx, hy, hr), fill=BK)
    # olhinho em terracota
    d.ellipse(P(hx - hr * 0.2, hy - hr * 0.2, hr * 0.28), fill=TR)


# coroa de serpentes (pares simétricos ao redor)
nsn = 12
for i in range(nsn):
    ang = (i / nsn) * 2 * math.pi - math.pi / 2
    snake(ang, face_r * 0.85, face_r * 0.20, face_r * 0.34, 3.0, i * 1.7)

# rosto: disco preto
d.ellipse(P(C, C, face_r), fill=BK)

# --- detalhes INCISOS em terracota (como riscado no verniz negro) ---
# contorno interno do rosto
d.ellipse(P(C, C, face_r * 0.93), outline=TR, width=int(face_r * 0.035))

# olhos: amêndoa em terracota, pupila preta (figuras negras deixam olho claro)
edx, edy, ew, eh = face_r * 0.42, -face_r * 0.05, face_r * 0.30, face_r * 0.19
for s in (-1, 1):
    ex, ey = C + s * edx, C + edy
    d.ellipse([ex - ew, ey - eh, ex + ew, ey + eh], fill=TR)            # esclera (terracota)
    d.ellipse(P(ex, ey, eh * 0.66), fill=BK)                            # íris preta
    d.ellipse(P(ex, ey, eh * 0.30), fill=TR)                           # reflexo
    # contorno do olho (linha preta dupla)
    d.ellipse([ex - ew, ey - eh, ex + ew, ey + eh], outline=BK, width=int(face_r * 0.03))
# sobrancelhas em V (incisas, terracota)
bw = int(face_r * 0.06)
d.line([C - edx - ew, C + edy - eh * 1.2, C - face_r * 0.05, C + edy - eh * 0.4], fill=TR, width=bw)
d.line([C + edx + ew, C + edy - eh * 1.2, C + face_r * 0.05, C + edy - eh * 0.4], fill=TR, width=bw)

# nariz: duas narinas + cana (incisão terracota)
ny = C + face_r * 0.26
d.line([C, C + edy + eh * 0.3, C, ny], fill=TR, width=int(face_r * 0.04))
d.ellipse(P(C - face_r * 0.055, ny, face_r * 0.045), fill=TR)
d.ellipse(P(C + face_r * 0.055, ny, face_r * 0.045), fill=TR)

# boca larga: faixa terracota com dentes pretos + presas
my, mw = C + face_r * 0.56, face_r * 0.40
d.rounded_rectangle([C - mw, my - face_r * 0.12, C + mw, my + face_r * 0.10],
                    radius=face_r * 0.10, fill=TR)
# dentes (riscos pretos verticais)
for k in range(-3, 4):
    x0 = C + k * (mw / 3.4)
    d.line([x0, my - face_r * 0.11, x0, my + face_r * 0.05], fill=BK, width=int(face_r * 0.02))
d.line([C - mw, my - face_r * 0.01, C + mw, my - face_r * 0.01], fill=BK, width=int(face_r * 0.02))
# presas (cantos)
d.polygon([(C - mw * 0.86, my - face_r * 0.01), (C - mw * 0.7, my - face_r * 0.01),
           (C - mw * 0.78, my + face_r * 0.07)], fill=BK)
d.polygon([(C + mw * 0.86, my - face_r * 0.01), (C + mw * 0.7, my - face_r * 0.01),
           (C + mw * 0.78, my + face_r * 0.07)], fill=BK)
# língua para fora (terracota), traço icônico
d.rounded_rectangle([C - face_r * 0.10, my + face_r * 0.05, C + face_r * 0.10, my + face_r * 0.30],
                    radius=face_r * 0.08, fill=TR)
d.line([C, my + face_r * 0.10, C, my + face_r * 0.27], fill=BK, width=int(face_r * 0.02))

out = Image.alpha_composite(base, fig)
icon = out.resize((OUT, OUT), Image.LANCZOS)
path = os.path.join(os.path.dirname(__file__) or ".", "aspis_icon_1024.png")
icon.save(path)
print("salvo:", path, icon.size)

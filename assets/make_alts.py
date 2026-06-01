#!/usr/bin/env python3
"""Conceitos MINIMALISTAS no traço grego clássico. Saída: /tmp/clipeo_alts.png.

A: Capacete coríntio em silhueta (perfil) — o emblema grego por excelência.
B: Meandro (greek key) em moldura quadrada, centro vazio — pura geometria grega.
C: Perfil de cabeça (estilo moeda/vaso) em silhueta limpa.

Paleta sóbria: terracota fosca + verniz quase-preto, 2 cores apenas.
"""
import math
import os

import numpy as np
from PIL import Image, ImageDraw

OUT = 512
SS = 2
W = OUT * SS
C = W / 2.0

TERRA = (190, 96, 52)
INK = (26, 20, 18, 255)


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def disc():
    ax = (np.arange(W) + 0.5) / W * 2 - 1
    xx, yy = np.meshgrid(ax, ax)
    se = (np.abs(xx / 0.94) ** 5.0 + np.abs(yy / 0.94) ** 5.0)
    bg_alpha = smoothstep(1.012, 0.988, se)
    g = (yy + 1) / 2
    n0 = np.array([0.09, 0.10, 0.14])
    bg = n0[None, None, :] * (1 - g[..., None]) + (n0 * 0.6)[None, None, :] * g[..., None]
    R = 0.76
    rr = np.sqrt(xx ** 2 + yy ** 2) / R
    shade = np.clip(1.05 - 0.16 * rr, 0.62, 1.05)
    t = np.array(TERRA) / 255.0
    d = np.clip(t[None, None, :] * shade[..., None], 0, 1)
    da = smoothstep(1.004, 0.996, rr)
    sh = smoothstep(1.13, 0.76, np.sqrt((xx - 0.03) ** 2 + (yy - 0.04) ** 2) / R) * 0.4
    img = bg * (1 - sh[..., None] * 0.9)
    aa = da[..., None]
    img = np.clip(img * (1 - aa) + d * aa, 0, 1)
    arr = (np.dstack([img, bg_alpha]) * 255 + 0.5).astype(np.uint8)
    return Image.fromarray(arr).convert("RGBA"), R


def smooth_closed(points, n=300):
    """Catmull-Rom fechado → lista densa de pontos (silhueta suave)."""
    pts = points
    m = len(pts)
    out = []
    for i in range(m):
        p0 = pts[(i - 1) % m]; p1 = pts[i]; p2 = pts[(i + 1) % m]; p3 = pts[(i + 2) % m]
        for j in range(n // m):
            t = j / (n // m)
            t2, t3 = t * t, t * t * t
            x = 0.5 * ((2 * p1[0]) + (-p0[0] + p2[0]) * t
                       + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2
                       + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3)
            y = 0.5 * ((2 * p1[1]) + (-p0[1] + p2[1]) * t
                       + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2
                       + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)
            out.append((x, y))
    return out


# ---------------- A: capacete coríntio (perfil, silhueta suave) -------------
def alt_A():
    base, R = disc()
    L = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    d = ImageDraw.Draw(L)
    s = R * C
    cx, cy = C + 0.04 * s, C + 0.02 * s
    # contorno do capacete voltado p/ a ESQUERDA (nasal à esquerda)
    pts = [
        (cx - 0.46 * s, cy - 0.02 * s),   # ponta do nasal (frente-baixo)
        (cx - 0.50 * s, cy - 0.18 * s),   # nasal sobe
        (cx - 0.34 * s, cy - 0.40 * s),   # testa
        (cx - 0.02 * s, cy - 0.52 * s),   # topo da cúpula
        (cx + 0.30 * s, cy - 0.40 * s),   # cúpula trás
        (cx + 0.40 * s, cy - 0.16 * s),
        (cx + 0.36 * s, cy + 0.10 * s),   # nuca
        (cx + 0.44 * s, cy + 0.40 * s),   # protetor de pescoço (flare)
        (cx + 0.16 * s, cy + 0.34 * s),
        (cx + 0.06 * s, cy + 0.16 * s),   # mandíbula interna
        (cx - 0.10 * s, cy + 0.44 * s),   # protetor frontal desce
        (cx - 0.30 * s, cy + 0.46 * s),
        (cx - 0.30 * s, cy + 0.14 * s),   # boca/queixo da máscara
        (cx - 0.40 * s, cy + 0.06 * s),
    ]
    d.polygon(smooth_closed(pts), fill=INK)
    # abertura do olho (recorte amendoado em terracota)
    ex, ey = cx - 0.16 * s, cy - 0.14 * s
    eye = [(ex - 0.16 * s, ey + 0.02 * s), (ex - 0.02 * s, ey - 0.07 * s),
           (ex + 0.16 * s, ey - 0.02 * s), (ex + 0.02 * s, ey + 0.08 * s)]
    d.polygon(smooth_closed(eye, 120), fill=(int(TERRA[0]), int(TERRA[1]), int(TERRA[2]), 255))
    # crista (penacho) como arco sólido fino sobre o topo
    cr = [(cx - 0.30 * s, cy - 0.52 * s), (cx - 0.05 * s, cy - 0.86 * s),
          (cx + 0.34 * s, cy - 0.72 * s), (cx + 0.30 * s, cy - 0.58 * s),
          (cx - 0.02 * s, cy - 0.66 * s), (cx - 0.22 * s, cy - 0.48 * s)]
    d.polygon(smooth_closed(cr, 160), fill=INK)
    return Image.alpha_composite(base, L)


# ---------------- B: meandro quadrado (greek key), centro vazio --------------
def alt_B():
    base, R = disc()
    L = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    d = ImageDraw.Draw(L)
    s = R * C
    lw = max(3, int(s * 0.055))
    half = s * 0.60
    # moldura quadrada de meandro: percorre os 4 lados com greek keys
    side = half * 2
    cells = 5                      # greek keys por lado
    step = side / cells
    def key_unit(ox, oy, ang):
        """desenha uma 'grega' numa célula step×step, orientada por ang (rad)."""
        ca, sa = math.cos(ang), math.sin(ang)
        def T(px, py):
            return (ox + px * ca - py * sa, oy + px * sa + py * ca)
        u = step
        # caminho da grega dentro da célula (coordenadas locais 0..u)
        p = [(0.0, 0.0), (0.0, 0.62 * u), (0.62 * u, 0.62 * u), (0.62 * u, 0.22 * u),
             (0.30 * u, 0.22 * u), (0.30 * u, 0.40 * u)]
        d.line([T(*q) for q in p], fill=INK, width=lw, joint="curve")
        d.line([T(0, 0), T(u, 0)], fill=INK, width=lw)  # base contínua
    # 4 lados
    for k in range(cells):
        key_unit(C - half + k * step, C - half, 0)            # topo
        key_unit(C + half, C - half + k * step, math.pi / 2)  # direita
        key_unit(C + half - k * step, C + half, math.pi)      # base
        key_unit(C - half, C + half - k * step, -math.pi / 2) # esquerda
    return Image.alpha_composite(base, L)


# ---------------- C: perfil de cabeça (moeda/vaso), silhueta -----------------
def alt_C():
    base, R = disc()
    L = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    d = ImageDraw.Draw(L)
    s = R * C
    cx, cy = C + 0.05 * s, C
    # perfil voltado à esquerda: testa, nariz reto (grego), lábios, queixo, nuca, cabelo
    pts = [
        (cx - 0.18 * s, cy - 0.50 * s),   # topo da cabeça
        (cx - 0.40 * s, cy - 0.30 * s),   # testa
        (cx - 0.46 * s, cy - 0.10 * s),   # linha nariz (grego: testa-nariz reto)
        (cx - 0.40 * s, cy + 0.02 * s),   # ponta do nariz
        (cx - 0.40 * s, cy + 0.10 * s),   # filtro
        (cx - 0.34 * s, cy + 0.16 * s),   # lábio sup
        (cx - 0.38 * s, cy + 0.22 * s),   # lábio inf
        (cx - 0.30 * s, cy + 0.34 * s),   # queixo
        (cx - 0.20 * s, cy + 0.46 * s),   # pescoço frente
        (cx + 0.10 * s, cy + 0.50 * s),
        (cx + 0.34 * s, cy + 0.30 * s),   # nuca/cabelo
        (cx + 0.40 * s, cy - 0.02 * s),
        (cx + 0.30 * s, cy - 0.34 * s),   # cabelo atrás
        (cx + 0.06 * s, cy - 0.50 * s),
    ]
    d.polygon(smooth_closed(pts), fill=INK)
    # olho (recorte terracota) + sobrancelha
    ex, ey = cx - 0.22 * s, cy - 0.14 * s
    d.ellipse([ex - 0.06 * s, ey - 0.035 * s, ex + 0.07 * s, ey + 0.045 * s],
              fill=(int(TERRA[0]), int(TERRA[1]), int(TERRA[2]), 255))
    d.ellipse([ex, ey - 0.02 * s, ex + 0.035 * s, ey + 0.02 * s], fill=INK)  # íris
    return Image.alpha_composite(base, L)


def fin(im, name):
    im = im.resize((OUT, OUT), Image.LANCZOS)
    im.save(f"/tmp/alt{name}.png")
    return im


a = fin(alt_A(), "A"); b = fin(alt_B(), "B"); c = fin(alt_C(), "C")
pad = 24
sheet = Image.new("RGB", (OUT * 3 + pad * 4, OUT + pad * 2 + 34), (245, 245, 247))
dd = ImageDraw.Draw(sheet)
for i, (im, lab) in enumerate([(a, "A  Capacete coríntio"), (b, "B  Meandro (greek key)"),
                               (c, "C  Perfil grego")]):
    x = pad + i * (OUT + pad)
    sheet.paste(im, (x, pad), im)
    dd.text((x + 8, pad + OUT + 8), lab, fill=(30, 30, 30))
sheet.save("/tmp/clipeo_alts.png")
print("salvo /tmp/clipeo_alts.png")

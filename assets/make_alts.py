#!/usr/bin/env python3
"""Gera 3 alternativas de ícone (escudo) para o Clípeo, lado a lado em
/tmp/clipeo_alts.png e cada uma em /tmp/alt{1,2,3}.png.

A: Gorgoneion gravado no bronze (o atual, refinado).
B: Silhueta minimalista — perfil da Medusa/serpente em traço único no disco.
C: Escudo-espelho — disco polido liso com um brilho/““reflexo”” e serpente em S.
"""
import math
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

SS = 2
OUT = 512
W = OUT * SS
C = W / 2.0


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def disc(metal="bronze"):
    """Retorna RGBA do fundo squircle + disco metálico."""
    ax = (np.arange(W) + 0.5) / W * 2 - 1
    xx, yy = np.meshgrid(ax, ax)
    se = (np.abs(xx / 0.94) ** 5.0 + np.abs(yy / 0.94) ** 5.0)
    bg_alpha = smoothstep(1.012, 0.988, se)
    g = (yy + 1) / 2
    bg = (np.array([0.115, 0.142, 0.212])[None, None, :] * (1 - g[..., None])
          + np.array([0.035, 0.047, 0.082])[None, None, :] * g[..., None])
    glow = np.clip(1 - np.sqrt((xx + 0.4) ** 2 + (yy + 0.4) ** 2) / 1.4, 0, 1) ** 2
    bg = np.clip(bg + glow[..., None] * np.array([0.05, 0.06, 0.09])[None, None, :], 0, 1)

    R = 0.72
    rr = np.sqrt(xx ** 2 + yy ** 2) / R
    dome = np.sqrt(np.clip(1 - np.clip(rr, 0, 1) ** 2, 0, 1))
    diag = (-(xx) - (yy)) / 1.5
    lum = np.clip(0.36 + 0.46 * (dome * 0.9 + 0.1) + 0.16 * diag, 0, 1)
    ringband = np.exp(-((rr - 0.9) ** 2) / (2 * 0.02 ** 2))
    lum = np.clip(lum - 0.16 * ringband, 0, 1)
    stops = np.array([0.00, 0.30, 0.55, 0.75, 0.90, 1.00])
    if metal == "bronze":
        pr = np.array([0x3a, 0x73, 0xad, 0xd9, 0xef, 0xff]) / 255
        pg = np.array([0x25, 0x49, 0x76, 0xa2, 0xc9, 0xf6]) / 255
        pb = np.array([0x10, 0x1b, 0x2b, 0x40, 0x66, 0xda]) / 255
    else:  # prata/aço polido (espelho)
        pr = np.array([0x3a, 0x60, 0x90, 0xc2, 0xe6, 0xff]) / 255
        pg = np.array([0x42, 0x68, 0x98, 0xc8, 0xea, 0xff]) / 255
        pb = np.array([0x4e, 0x74, 0xa4, 0xd2, 0xf0, 0xff]) / 255
    met = np.stack([np.interp(lum, stops, pr),
                    np.interp(lum, stops, pg),
                    np.interp(lum, stops, pb)], axis=-1)
    rim = smoothstep(0.965, 0.995, rr) * smoothstep(1.02, 0.995, rr)
    met = met * (1 - 0.55 * rim[..., None])
    da = smoothstep(1.004, 0.996, rr)
    sh = smoothstep(1.16, 0.7, np.sqrt((xx - 0.04) ** 2 + (yy - 0.05) ** 2) / R) * 0.5
    img = bg * (1 - sh[..., None] * 0.9)
    aa = da[..., None]
    img = np.clip(img * (1 - aa) + met * aa, 0, 1)
    arr = (np.dstack([img, bg_alpha]) * 255 + 0.5).astype(np.uint8)
    return Image.fromarray(arr).convert("RGBA"), R


def P(cx, cy, r):
    return [cx - r, cy - r, cx + r, cy + r]


# ---------------- A: Gorgoneion gravado (atual) ----------------
def alt_A():
    base, R = disc("bronze")
    layer = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    LO = (96, 70, 30, 255); LO2 = (60, 43, 18, 255)
    HI = (245, 224, 150, 255); MID = (181, 140, 70, 255)
    face_r = R * C * 0.46
    n = 10; ring_r = face_r * 1.02
    for i in range(n):
        ang = (i / n) * 2 * math.pi - math.pi / 2
        bx, by = C + math.cos(ang) * ring_r, C + math.sin(ang) * ring_r
        seglen = face_r * 0.62; nb = 5; pts = []
        for j in range(nb):
            t = j / (nb - 1); perp = ang + math.pi / 2
            wob = math.sin(t * math.pi * 1.6 + i * 1.3) * face_r * 0.22
            px = bx + math.cos(ang) * seglen * t + math.cos(perp) * wob
            py = by + math.sin(ang) * seglen * t + math.sin(perp) * wob
            pts.append((px, py, face_r * (0.20 * (1 - 0.45 * t))))
        for px, py, rad in pts: d.ellipse(P(px, py, rad + face_r * 0.05), fill=LO2)
        for px, py, rad in pts: d.ellipse(P(px, py, rad), fill=MID)
        for px, py, rad in pts: d.ellipse(P(px - rad * .35, py - rad * .35, rad * .42), fill=HI)
    d.ellipse(P(C, C, face_r + face_r * 0.05), fill=LO2)
    d.ellipse(P(C, C, face_r), fill=MID)
    edx, edy, ew, eh = face_r * .40, -face_r * .06, face_r * .30, face_r * .20
    for s in (-1, 1):
        ex, ey = C + s * edx, C + edy
        d.ellipse([ex-ew, ey-eh, ex+ew, ey+eh], fill=LO2)
        d.ellipse([ex-ew*.86, ey-eh*.82, ex+ew*.86, ey+eh*.82], fill=HI)
        d.ellipse(P(ex, ey, eh*.62), fill=LO2); d.ellipse(P(ex, ey, eh*.30), fill=(15,12,8,255))
    bw = int(face_r*.10)
    d.line([C-edx-ew, C+edy-eh*1.25, C-face_r*.06, C+edy-eh*.45], fill=LO2, width=bw)
    d.line([C+edx+ew, C+edy-eh*1.25, C+face_r*.06, C+edy-eh*.45], fill=LO2, width=bw)
    my, mw = C+face_r*.58, face_r*.40
    d.ellipse([C-mw, my-face_r*.14, C+mw, my+face_r*.16], fill=(20,12,8,255))
    d.rectangle([C-mw*.82, my-face_r*.12, C+mw*.82, my-face_r*.03], fill=HI)
    d.ellipse([C-face_r*.13, my, C+face_r*.13, my+face_r*.30], fill=(150,55,48,255))
    return Image.alpha_composite(base, layer)


# ---------------- B: silhueta minimalista (cabeça + 2 serpentes em traço) ------
def alt_B():
    base, R = disc("bronze")
    layer = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    INK = (44, 30, 12, 255)
    face_r = R * C * 0.40
    lw = int(face_r * 0.13)
    # rosto: círculo em traço
    d.ellipse(P(C, C, face_r), outline=INK, width=lw)
    # dois olhos (preenchidos) + sobrancelha reta
    edx, eh = face_r*.42, face_r*.13
    for s in (-1, 1):
        d.ellipse(P(C + s*edx, C - face_r*.05, eh), fill=INK)
    d.line([C-edx-eh, C-face_r*.30, C+edx+eh, C-face_r*.30], fill=INK, width=int(lw*.7))
    # boca: arco simples
    d.arc([C-face_r*.45, C+face_r*.05, C+face_r*.45, C+face_r*.6], 20, 160, fill=INK, width=lw)
    # serpentes: dois arcos simétricos saindo do topo, em S
    for s in (-1, 1):
        cx = C + s*face_r*0.5
        d.arc([cx - face_r*0.9, C - face_r*1.7, cx + face_r*0.9, C - face_r*0.1],
              200 if s<0 else 250, 340 if s<0 else 20, fill=INK, width=lw)
        # cabecinha
        hx = C + s*face_r*1.25
        d.ellipse(P(hx, C - face_r*1.0, face_r*0.16), fill=INK)
    return Image.alpha_composite(base, layer)


# ---------------- C: escudo-espelho (prata polido + serpente em S) -------------
def alt_C():
    base, R = disc("silver")
    layer = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    INK = (40, 60, 80, 230)
    # serpente única em S vertical (símbolo do reflexo/vigilância)
    lw = int(R*C*0.10)
    pts = []
    for k in range(40):
        t = k/39
        yy = C - R*C*0.62 + t * (R*C*1.24)
        xx = C + math.sin(t*math.pi*2.0) * R*C*0.30
        pts.append((xx, yy))
    d.line(pts, fill=INK, width=lw, joint="curve")
    # cabeça (triângulo arredondado) no topo
    hx, hy = pts[0]
    d.ellipse(P(hx, hy, R*C*0.13), fill=INK)
    d.ellipse(P(hx - R*C*0.04, hy - R*C*0.02, R*C*0.03), fill=(240,240,245,255))  # olho
    # faixa de brilho diagonal (espelho)
    glare = Image.new("RGBA", (W, W), (0,0,0,0))
    gd = ImageDraw.Draw(glare)
    gd.ellipse([C-R*C*0.95, C-R*C*0.95, C+R*C*0.2, C-R*C*0.1], fill=(255,255,255,40))
    glare = glare.filter(ImageFilter.GaussianBlur(W/60))
    out = Image.alpha_composite(base, glare)
    return Image.alpha_composite(out, layer)


def finish(im, name):
    im = im.resize((OUT, OUT), Image.LANCZOS)
    im.save(f"/tmp/{name}.png")
    return im


a = finish(alt_A(), "altA")
b = finish(alt_B(), "altB")
c = finish(alt_C(), "altC")

# painel lado a lado com rótulos
pad, labelh = 24, 40
sheet = Image.new("RGBA", (OUT*3 + pad*4, OUT + labelh + pad*2), (245, 245, 247, 255))
dd = ImageDraw.Draw(sheet)
for i, (im, lab) in enumerate([(a, "A  Gorgoneion"), (b, "B  Silhueta"), (c, "C  Espelho")]):
    x = pad + i*(OUT+pad)
    sheet.paste(im, (x, pad), im)
    dd.text((x + 8, pad + OUT + 8), lab, fill=(30, 30, 30, 255))
sheet.convert("RGB").save("/tmp/clipeo_alts.png")
print("salvo /tmp/clipeo_alts.png")

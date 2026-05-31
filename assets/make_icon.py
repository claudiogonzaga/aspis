#!/usr/bin/env python3
"""Gera o ícone do Clípeo: um clipeus (escudo redondo) de bronze polido,
inspirado no escudo-espelho de Perseu.

Saída: assets/clipeo_icon_1024.png (mestre 1024x1024, fundo arredondado).
A partir dele, build_icns.sh gera o .icns com todos os tamanhos.

Técnica: modela a superfície do escudo como um height field (boss central
abaulado + rim biselado + anéis incisos), calcula normais e aplica
iluminação difusa + especular (luz no alto-esquerda) para o brilho metálico.
Renderiza em 2x e reduz com LANCZOS para antialiasing.
"""
import numpy as np
from PIL import Image

OUT = 1024
W = OUT * 2  # supersampling

# ---- grids centrados (-1..1 em relação a meia-largura) ----
ax = (np.arange(W) + 0.5) / W * 2 - 1  # -1..1
xx, yy = np.meshgrid(ax, ax)


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def normalize(vx, vy, vz):
    n = np.sqrt(vx * vx + vy * vy + vz * vz) + 1e-9
    return vx / n, vy / n, vz / n


# =========================================================
# 1) FUNDO: squircle (superelipse) com gradiente noturno
# =========================================================
A = 0.94  # meia-extensão do squircle (deixa margem p/ corner do macOS)
N_SE = 5.0
se = (np.abs(xx / A) ** N_SE + np.abs(yy / A) ** N_SE)
bg_mask = smoothstep(1.0 + 0.012, 1.0 - 0.012, se)  # 1 dentro, 0 fora

# gradiente vertical: topo grafite-azulado -> base quase preto
top = np.array([0.118, 0.145, 0.216])   # #1e2537
bot = np.array([0.039, 0.051, 0.086])   # #0a0d16
g = (yy + 1) / 2
bg = top[None, None, :] * (1 - g[..., None]) + bot[None, None, :] * g[..., None]
# vinheta radial sutil (escurece cantos)
rad = np.sqrt(xx ** 2 + yy ** 2)
vig = 1 - 0.22 * smoothstep(0.2, 1.3, rad)
bg = bg * vig[..., None]
# brilho ambiente suave no alto-esquerda
glow = np.clip(1 - np.sqrt((xx + 0.45) ** 2 + (yy + 0.45) ** 2) / 1.4, 0, 1) ** 2
bg = bg + glow[..., None] * np.array([0.05, 0.06, 0.09])[None, None, :]
bg = np.clip(bg, 0, 1)

# =========================================================
# 2) ESCUDO: height field + iluminação
# =========================================================
R = 0.70                    # raio do escudo (em unidades de meia-largura)
dist = np.sqrt(xx ** 2 + yy ** 2)
rr = dist / R               # 0 no centro, 1 na borda

# --- height field h(rr) ---
h = np.zeros_like(rr)

# rim (borda elevada) entre rimIn..1.0, perfil arredondado
rimIn = 0.78
trim = np.clip((rr - rimIn) / (1.0 - rimIn), 0, 1)
rim_profile = np.sin(np.pi * trim)            # 0 nas pontas, 1 no meio do rim
h += 0.22 * rim_profile * (rr <= 1.0)

# campo levemente côncavo entre boss e rim
field = (rr > 0.24) & (rr < rimIn)
h += -0.04 * np.cos(np.pi * np.clip((rr - 0.24) / (rimIn - 0.24), 0, 1)) * field

# boss central (umbo) abaulado
bossR = 0.26
dome = np.sqrt(np.clip(1 - (rr / bossR) ** 2, 0, 1))
h += 0.42 * dome

# bico central (ponta do umbo)
tipR = 0.06
h += 0.10 * np.sqrt(np.clip(1 - (rr / tipR) ** 2, 0, 1))

# anéis concêntricos incisos (sulcos finos) — vales gaussianos
for rc in (0.40, 0.58, 0.70):
    h -= 0.05 * np.exp(-((rr - rc) ** 2) / (2 * 0.012 ** 2))

# --- normais a partir do gradiente do height field ---
# escala o gradiente para acentuar o relevo
gy, gx = np.gradient(h)
scale = W * 0.018
nx, ny, nz = normalize(-gx * scale, -gy * scale, np.ones_like(h))

# --- luz: alto-esquerda, ligeiramente frontal ---
lx, ly, lz = normalize(-0.55, -0.55, 0.78)
diff = np.clip(nx * lx + ny * ly + nz * lz, 0, 1)

# especular (Blinn-Phong) — meio-vetor com o olho em +z
hx, hy, hz = normalize(lx, ly, lz + 1.0)
spec = np.clip(nx * hx + ny * hy + nz * hz, 0, 1) ** 36.0

# luminância metálica: ambiente + difusa + sheen direcional
proj = (-(xx) - (yy)) / 1.45           # gradiente diagonal (polimento)
lum = 0.20 + 0.86 * diff + 0.20 * proj
lum = np.clip(lum, 0, 1)

# --- paleta bronze/ouro: L -> cor (sombras abronzeadas, realce ouro pálido) ---
stops = np.array([0.00, 0.28, 0.48, 0.66, 0.80, 0.92, 1.00])
pal_r = np.array([0x2c, 0x5e, 0x9a, 0xcb, 0xea, 0xfa, 0xff]) / 255
pal_g = np.array([0x18, 0x39, 0x66, 0x96, 0xbf, 0xe4, 0xfd]) / 255
pal_b = np.array([0x09, 0x12, 0x22, 0x33, 0x57, 0xa6, 0xee]) / 255
shield_rgb = np.stack([
    np.interp(lum, stops, pal_r),
    np.interp(lum, stops, pal_g),
    np.interp(lum, stops, pal_b),
], axis=-1)

# realce especular branco-dourado por cima
shield_rgb = shield_rgb + spec[..., None] * np.array([0.95, 0.85, 0.55])[None, None, :]

# sulcos escuros marcados (reforça as linhas concêntricas)
groove = np.zeros_like(rr)
for rc in (0.40, 0.58, 0.70):
    groove += np.exp(-((rr - rc) ** 2) / (2 * 0.008 ** 2))
shield_rgb = shield_rgb * (1 - 0.28 * groove[..., None])

# faixa de "espelho polido": brilho diagonal suave no alto-esquerda
streak = np.clip(1 - np.abs((xx + yy) + 0.55) / 0.45, 0, 1) ** 2
streak = streak * smoothstep(1.0, 0.6, rr)  # só dentro do escudo
shield_rgb = shield_rgb + streak[..., None] * np.array([0.20, 0.18, 0.12])[None, None, :]

shield_rgb = np.clip(shield_rgb, 0, 1)

# máscara do disco do escudo (AA na borda)
shield_a = smoothstep(1.0 + 0.006, 1.0 - 0.006, rr)

# =========================================================
# 3) SOMBRA do escudo sobre o fundo
# =========================================================
sh_dist = np.sqrt((xx - 0.045) ** 2 + (yy - 0.06) ** 2) / R
shadow = smoothstep(1.18, 0.62, sh_dist) * 0.55

# =========================================================
# 4) COMPOSIÇÃO
# =========================================================
img = bg.copy()
# aplica sombra (escurece) dentro do fundo
img = img * (1 - shadow[..., None] * 0.9)
# compõe escudo
a = shield_a[..., None]
img = img * (1 - a) + shield_rgb * a
img = np.clip(img, 0, 1)

# alpha final = squircle do fundo (cantos transparentes)
alpha = bg_mask
rgba = np.dstack([img, alpha])
arr = (rgba * 255 + 0.5).astype(np.uint8)

im = Image.fromarray(arr, "RGBA").resize((OUT, OUT), Image.LANCZOS)
import os
os.makedirs(os.path.dirname(__file__) or ".", exist_ok=True)
path = os.path.join(os.path.dirname(__file__) or ".", "clipeo_icon_1024.png")
im.save(path)
print("salvo:", path, im.size)

"""Modelo de trajetória.

Porte fiel de `TCalculador::calcular` (Plugins/Aimbot/subplugin/calculador.cpp).
As constantes de `mobiles.py` foram calibradas contra ESTE integrador, por isso
as peculiaridades foram mantidas:

  * passo fixo TICK = 0.05, até 1001 passos (t de 0 a 50);
  * a "velocidade acumulada" (us) é somada à posição SEM multiplicar por TICK;
  * a força do vento é truncada para inteiro em cada eixo antes de aplicar o efeito;
  * cos(ângulo) recebe ±0.002 conforme o lado (o Grub tem correção própria).

Coordenadas: as da tela (x para a direita, y para BAIXO). Ângulos em graus na
convenção matemática (0 = direita, 90 = para cima).

Equações por passo (a = vento, g = gravidade, v0 = força·(cos, sin)):
    x += v0x·T + usx + ax·T²/2          usx += ax·T
    y -= v0y·T + usy + (ay − g)·T²/2    usy += (ay − g)·T
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .mobiles import Mobile

TICK = 0.05
PASSOS_MAX = 1001


@dataclass(frozen=True)
class Vento:
    forca: int = 0
    angulo: float = 0.0  # graus, convenção matemática (para onde o vento sopra)


@dataclass(frozen=True)
class Limites:
    """Quando o projétil sai desta caixa a simulação para (original: 0..1800, -5000..2000).
    `tornados`: faixas (x_ini, x_fim) de tornados marcados na tela (ver passar_tornado)."""
    x_min: float = -1000.0
    x_max: float = 2800.0
    y_min: float = -5000.0
    y_max: float = 2000.0
    tornados: tuple = ()


VOLTAS_TORNADO = 3


def passar_tornado(x, y, nx, ny, x_ini, x_fim):
    """TShMatrix::calculaTornado do CMX. Quando o passo (x,y)->(nx,ny) ENTRA na faixa
    [x_ini, x_fim] vindo de fora, o tiro dá 3 voltas de uma borda à outra; cada volta
    sobe/desce inclinação × largura, seguindo a inclinação com que entrou, e ele sai pela
    borda oposta com a mesma velocidade. Devolve (pontos do zigue-zague, saída) ou None."""
    if not (x_ini <= nx <= x_fim) or x_ini <= x <= x_fim or nx == x:
        return None
    s = (ny - y) / (nx - x)                       # inclinação na tela (y para baixo)
    borda, longe = (x_ini, x_fim) if x < x_ini else (x_fim, x_ini)
    yy = y + s * (borda - x)                      # ponto exato de entrada
    passo = s * (x_fim - x_ini) * (1 if nx > x else -1)
    pts = [(borda, yy)]
    for i in range(VOLTAS_TORNADO):
        yy += passo
        pts.append((longe if i % 2 == 0 else borda, yy))
    return pts, pts[-1]


def angulo_absoluto(angulo_hud: float, direita: bool) -> float:
    """Converte o ângulo mostrado no HUD para o ângulo do disparo (GetBotAngle do original)."""
    return angulo_hud % 360 if direita else (180 - angulo_hud) % 360


def vento_quantizado(vento: Vento) -> tuple[int, int]:
    """Componentes inteiras do vento, truncadas como o C fazia com (int)."""
    gama = math.cos(math.radians(vento.angulo))
    delta = math.sin(math.radians(vento.angulo))
    qx = int(gama * vento.forca + (-1e-4 if gama < 0 else 1e-4))
    qy = int(delta * vento.forca + (-1e-4 if delta < 0 else 1e-4))
    return qx, qy


def parametros(angulo_abs, gravidade, grub: bool, direita: bool):
    """Retorna (alfa, beta, g). Aceita escalares ou arrays numpy para ângulo/gravidade."""
    a = np.radians(angulo_abs)
    if grub:
        alfa = np.cos(a) - (0.053 - 0.0002 * np.asarray(angulo_abs, dtype=float))
        g = gravidade + (0.004 * np.asarray(angulo_abs, dtype=float) - 0.01)
    else:
        alfa = np.cos(a) + (-0.002 if direita else 0.002)
        g = gravidade
    return alfa, np.sin(a), g


def simular(angulo_abs: float, forca: float, origem: tuple[float, float], vento: Vento,
            mobile: Mobile, direita: bool, limites: Limites = Limites()) -> list[tuple[float, float]]:
    """Trajetória ponto a ponto (para desenhar)."""
    alfa, beta, g = (float(v) for v in parametros(angulo_abs, mobile.gravidade, mobile.grub, direita))
    qx, qy = vento_quantizado(vento)
    ax, ay = qx * mobile.efeito, qy * mobile.efeito
    vx, vy = alfa * forca, beta * forca
    meio = TICK * TICK * 0.5

    x, y = map(float, origem)
    usx = usy = 0.0
    pontos = [(x, y)]
    for _ in range(PASSOS_MAX):
        x0, y0 = x, y
        x += vx * TICK + usx + ax * meio
        y -= vy * TICK + usy + (ay - g) * meio
        usx += ax * TICK
        usy += (ay - g) * TICK
        for a, b in limites.tornados:
            t = passar_tornado(x0, y0, x, y, a, b)
            if t is not None:
                pontos += t[0][:-1]
                x, y = t[1]
                break
        pontos.append((x, y))
        if not (limites.x_min <= x <= limites.x_max and limites.y_min <= y <= limites.y_max):
            break
    return pontos


def varrer(alfa, beta, g, ax, ay, forcas, origem, alvo, limites: Limites = Limites()):
    """Simula muitas trajetórias de uma vez (todos os argumentos fazem broadcast).

    Para cada trajetória devolve a menor distância entre o ALVO e a curva
    (distância ponto-segmento, mais precisa que só olhar os vértices) e o ponto
    da curva onde isso acontece.

    Retorna (dist, px, py), arrays com o shape do broadcast.
    """
    alfa, beta, g, ax, ay, forcas = np.broadcast_arrays(
        *(np.asarray(v, dtype=float) for v in (alfa, beta, g, ax, ay, forcas)))
    vx = alfa * forcas * TICK
    vy = beta * forcas * TICK
    meio = TICK * TICK * 0.5
    ax_m, ayg_m = ax * meio, (ay - g) * meio
    ax_t, ayg_t = ax * TICK, (ay - g) * TICK
    tx, ty = float(alvo[0]), float(alvo[1])

    x = np.full(vx.shape, float(origem[0]))
    y = np.full(vx.shape, float(origem[1]))
    usx = np.zeros(vx.shape)
    usy = np.zeros(vx.shape)
    vivo = np.ones(vx.shape, dtype=bool)
    melhor = np.hypot(x - tx, y - ty)
    px, py = x.copy(), y.copy()

    for _ in range(PASSOS_MAX):
        nx = x + vx + usx + ax_m
        ny = y - (vy + usy + ayg_m)
        usx += ax_t
        usy += ayg_t
        for a, b in limites.tornados:             # passar_tornado, para todas as trajetórias de uma vez
            entra = vivo & (nx >= a) & (nx <= b) & ~((x >= a) & (x <= b)) & (nx != x)
            if entra.any():
                s = (ny - y) / np.where(nx == x, 1.0, nx - x)
                de_esq = x < a
                borda, longe = np.where(de_esq, a, b), np.where(de_esq, b, a)
                yy = y + s * (borda - x) + VOLTAS_TORNADO * s * (b - a) * np.sign(nx - x)
                nx = np.where(entra, longe, nx)
                ny = np.where(entra, yy, ny)

        dx, dy = nx - x, ny - y
        l2 = dx * dx + dy * dy
        t = np.clip(((tx - x) * dx + (ty - y) * dy) / np.where(l2 == 0, 1.0, l2), 0.0, 1.0)
        cx, cy = x + t * dx, y + t * dy
        d = np.hypot(cx - tx, cy - ty)

        melhora = vivo & (d < melhor)
        melhor = np.where(melhora, d, melhor)
        px = np.where(melhora, cx, px)
        py = np.where(melhora, cy, py)

        x, y = nx, ny
        vivo &= (x >= limites.x_min) & (x <= limites.x_max) & (y >= limites.y_min) & (y <= limites.y_max)
        if not vivo.any():
            break
    return melhor, px, py

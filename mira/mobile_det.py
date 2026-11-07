"""Detecção do próprio mobile pela agulha de ângulo.

No seu turno o jogo desenha, em volta do canhão, um setor cinza com a faixa
verde de ângulos permitidos e uma AGULHA vermelha apontando para o ângulo atual.
A agulha é:
  * um traço fino e alongado de cor laranja-avermelhada;
  * com direção = ângulo do HUD (virado para a direita) ou 180 − ângulo (esquerda).

Então: máscara de cor -> componentes conexos -> PCA de cada componente ->
fica o componente alongado cuja direção bate com um dos dois candidatos.
A base da agulha (ponta oposta à direção) é a origem do tiro, e o candidato
escolhido diz para que lado o mobile está virado.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Agulha:
    origem: tuple[int, int]
    direita: bool
    angulo_medido: float   # direção da agulha em graus (convenção matemática)
    comprimento: float
    pixels: int


def mascara_agulha(img: np.ndarray, cfg: dict) -> np.ndarray:
    r, g, b = (img[..., i].astype(int) for i in range(3))
    m = (r >= cfg["r_min"]) & (g <= cfg["g_max"]) & (b <= cfg["b_max"]) & (r - g >= cfg["r_menos_g"])
    x0, y0, x1, y1 = cfg["area"]
    fora = np.ones_like(m)
    fora[y0:y1, x0:x1] = False
    m[fora] = False
    for ex0, ey0, ex1, ey1 in cfg.get("excluir", []):
        m[ey0:ey1, ex0:ex1] = False
    return m


def componentes(m: np.ndarray, min_pixels: int) -> list[np.ndarray]:
    """Componentes 8-conexos (flood fill simples; a máscara costuma ter poucos pixels)."""
    restantes = {(int(y), int(x)) for y, x in zip(*np.nonzero(m))}
    saida = []
    while restantes:
        semente = restantes.pop()
        pilha, comp = [semente], [semente]
        while pilha:
            y, x = pilha.pop()
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    v = (y + dy, x + dx)
                    if v in restantes:
                        restantes.remove(v)
                        pilha.append(v)
                        comp.append(v)
        if len(comp) >= min_pixels:
            saida.append(np.array(comp, dtype=float))
    return saida


def _dif_eixo(a: float, b: float) -> float:
    """Diferença entre duas direções de EIXO (módulo 180°)."""
    d = abs(a - b) % 180
    return min(d, 180 - d)


def detectar_agulha(img: np.ndarray, angulo_hud: int, cfg: dict) -> Agulha | None:
    m = mascara_agulha(img, cfg)
    candidatos = {True: angulo_hud % 360, False: (180 - angulo_hud) % 360}
    melhor: tuple[float, Agulha] | None = None
    for comp in componentes(m, cfg["min_pixels"]):
        ys, xs = comp[:, 0], comp[:, 1]
        cx, cy = xs.mean(), ys.mean()
        cov = np.cov(np.vstack([xs - cx, -(ys - cy)]))   # y para cima
        autoval, autovet = np.linalg.eigh(cov)
        if autoval[0] <= 1e-6:
            autoval[0] = 1e-6
        alongamento = math.sqrt(autoval[1] / autoval[0])
        if alongamento < cfg["alongamento_min"]:
            continue
        ux, uy = autovet[:, 1]
        eixo = math.degrees(math.atan2(uy, ux)) % 180
        for direita, alvo in candidatos.items():
            dif = _dif_eixo(eixo, alvo)
            if dif > cfg["tolerancia_graus"]:
                continue
            # orienta o eixo no sentido do ângulo alvo e acha a base (ponta oposta)
            t = math.radians(alvo)
            dx, dy = math.cos(t), math.sin(t)
            proj = (xs - cx) * dx + (-(ys - cy)) * dy
            comprimento = float(proj.max() - proj.min())
            if comprimento < cfg["comprimento_min"]:
                continue
            base = proj <= np.percentile(proj, 5)
            origem = (int(round(xs[base].mean())), int(round(ys[base].mean())))
            medido = math.degrees(math.atan2(uy * np.sign(ux * dx + uy * dy), ux * np.sign(ux * dx + uy * dy))) % 360
            nota = dif - 0.05 * comprimento   # prefere alinhado e comprido
            ag = Agulha(origem, direita, medido, comprimento, len(xs))
            if melhor is None or nota < melhor[0]:
                melhor = (nota, ag)
    return melhor[1] if melhor else None

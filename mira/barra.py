"""Leitura da barra de força do Thor's Hammer (800x600).

Medido em gravação a ~89 fps (capturas/gravacao):
  * pino (marcador que o jogador arrasta): na linha y=556, uma faixa escura entre o
    mapa e a moldura, só o pino aparece claro (padrão  +##.#.##+  com ~9 px);
  * carga: enquanto o espaço está pressionado, colunas acesas CONTÍNUAS na linha
    y=580 a partir de x0+1;
  * tiro anterior: depois de soltar, sobra só um traço isolado na força usada.
força = (x − x0) / escala
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class LeituraBarra:
    pino: int | None          # força marcada pelo pino
    carga: int | None         # força atual enquanto carrega (None = não está carregando)
    anterior: int | None      # força do último tiro (traço isolado)


def _lum_linha(img: np.ndarray, y: int, x0: int, x1: int) -> np.ndarray:
    linha = img[y, x0:x1].astype(float)
    return linha @ np.array([0.299, 0.587, 0.114])


def ler_barra(img: np.ndarray, cfg: dict) -> LeituraBarra:
    x0, esc = cfg["x0"], cfg["escala"]
    fmax = cfg.get("forca_max", 400)
    x_fim = int(x0 + fmax * esc) + 2

    # pino
    pino = None
    lum = _lum_linha(img, cfg["pino_y"], x0 - 8, x_fim + 8)
    claros = np.nonzero(lum > cfg.get("pino_limiar", 150))[0]
    if len(claros):
        largura = claros.max() - claros.min() + 1
        if 3 <= largura <= 14:
            centro = (claros.min() + claros.max()) / 2 + (x0 - 8)
            pino = int(round((centro - x0) / esc))

    # carga e tiro anterior
    lum = _lum_linha(img, cfg["linha_y"], x0, x_fim)
    acesas = lum > cfg.get("carga_limiar", 60)
    i = 1
    while i < len(acesas) and acesas[i]:
        i += 1
    fim_carga = i - 1                     # última coluna contínua acesa
    carga = int(round((fim_carga + 1) / esc)) if fim_carga >= cfg.get("carga_min_px", 3) else None
    isoladas = np.nonzero(acesas[i:])[0]
    anterior = int(round((isoladas[-1] + i) / esc)) if len(isoladas) else None
    return LeituraBarra(pino, carga, anterior)

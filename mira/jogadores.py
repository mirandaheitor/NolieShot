"""Acha as etiquetas de nome dos jogadores no mapa e separa os times pela cor.

Toda etiqueta começa com a bandeira do país (ícone 26x16, igual para todos os BR),
seguida do nome na cor do time (azul ou laranja). Procura a bandeira com
cv2.matchTemplate e lê o tom dos pixels coloridos logo à direita dela.
O seu time é o da etiqueta mais perto da sua origem; rival = o outro time.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


@dataclass(frozen=True)
class Etiqueta:
    x: int          # canto superior esquerdo da bandeira
    y: int
    time: str       # "azul", "laranja" ou "?"
    score: float


def time_da_cor(nome_rgb: np.ndarray) -> str:
    """Tom médio dos pixels coloridos do nome: azul (aliado/rival depende da partida) ou laranja."""
    a = nome_rgb.astype(int)
    m = (a.max(axis=2) - a.min(axis=2) >= 50) & (a.max(axis=2) >= 120)
    if m.sum() < 15:
        return "?"
    r, _, b = a[m].mean(axis=0)
    if b > r + 20:
        return "azul"
    if r > b + 40:
        return "laranja"
    return "?"


class Jogadores:
    def __init__(self, arq_bandeira: Path, limiar: float = 0.85, excluir=(), y_max: int = 515):
        self.bandeira = (np.asarray(Image.open(arq_bandeira).convert("RGB"))
                         if Path(arq_bandeira).exists() else None)
        self.limiar, self.excluir, self.y_max = limiar, [tuple(r) for r in excluir], y_max

    @property
    def pronto(self) -> bool:
        return self.bandeira is not None

    def achar(self, img: np.ndarray) -> list[Etiqueta]:
        if self.bandeira is None:
            return []
        h, w = self.bandeira.shape[:2]
        area = np.ascontiguousarray(img[:self.y_max])
        if area.shape[0] < h or area.shape[1] < w:
            return []
        res = cv2.matchTemplate(area, self.bandeira, cv2.TM_CCOEFF_NORMED)
        ys, xs = np.nonzero(res >= self.limiar)
        achadas: list[Etiqueta] = []
        for i in np.argsort(-res[ys, xs]):                       # melhores primeiro, sem repetir vizinhos
            x, y = int(xs[i]), int(ys[i])
            if any(abs(x - e.x) <= 10 and abs(y - e.y) <= 8 for e in achadas):
                continue
            if any(x0 <= x < x1 and y0 <= y < y1 for x0, y0, x1, y1 in self.excluir):
                continue                                         # lista de turnos etc.
            nome = img[y + 2:y + h - 2, x + w + 1:x + w + 64]
            achadas.append(Etiqueta(x, y, time_da_cor(nome), float(res[y, x])))
        return achadas


def mais_perto(etiquetas, ponto, raio: float | None = None):
    if ponto is None or not etiquetas:
        return None
    melhor = min(etiquetas, key=lambda e: (e.x - ponto[0]) ** 2 + (e.y - ponto[1]) ** 2)
    if raio is not None and (melhor.x - ponto[0]) ** 2 + (melhor.y - ponto[1]) ** 2 > raio ** 2:
        return None
    return melhor

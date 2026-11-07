"""Acompanha a rolagem da câmera comparando cada quadro com o anterior.

Correlação de fase (cv2.phaseCorrelate) só na área do mapa, em resolução cheia
(~10 ms por quadro em 800x460; com meia resolução erra ~1 px a cada 50). O resultado é quanto o MAPA andou na tela: pontos fixos no
mapa (origem, alvo) devem ser deslocados do mesmo tanto. Assim dá para rolar a
tela até o inimigo e a trajetória continua saindo do seu mobile fora da tela.

Leituras com confiança baixa são descartadas: animações grandes (tornado, efeitos)
dão deslocamentos falsos com resposta ~0.2; a câmera de verdade fica acima de ~0.5.
"""
from __future__ import annotations

import cv2
import numpy as np


class Camera:
    def __init__(self, area, resp_min: float = 0.4, max_px: float = 150, minimo: float = 0.75,
                 escala: float = 1.0):
        self.area = [int(v) for v in area]     # x0, y0, x1, y1 (área cliente)
        self.resp_min, self.max_px, self.minimo, self.escala = resp_min, max_px, minimo, escala
        self._ant: np.ndarray | None = None
        self._janela: np.ndarray | None = None
        self._resto = np.zeros(2)

    def _preparar(self, img: np.ndarray) -> np.ndarray | None:
        x0, y0, x1, y1 = self.area
        rec = img[y0:y1, x0:x1]
        if rec.size == 0:
            return None
        cinza = cv2.cvtColor(np.ascontiguousarray(rec), cv2.COLOR_RGB2GRAY).astype(np.float32)
        return cv2.resize(cinza, None, fx=self.escala, fy=self.escala, interpolation=cv2.INTER_AREA)

    def reiniciar(self) -> None:
        self._ant, self._resto = None, np.zeros(2)

    def medir(self, img: np.ndarray) -> tuple[int, int]:
        """(dx, dy) inteiros que o mapa andou na tela desde o quadro anterior."""
        atual = self._preparar(img)
        if atual is None:
            return 0, 0
        ant, self._ant = self._ant, atual
        if ant is None or ant.shape != atual.shape:
            self._janela = cv2.createHanningWindow(atual.shape[::-1], cv2.CV_32F)
            return 0, 0
        (dx, dy), resp = cv2.phaseCorrelate(ant, atual, self._janela)
        dx, dy = dx / self.escala, dy / self.escala
        if resp < self.resp_min or np.hypot(dx, dy) > self.max_px:
            return 0, 0
        if abs(dx) < self.minimo and abs(dy) < self.minimo:   # ruído com a câmera parada
            return 0, 0
        total = self._resto + (dx, dy)                       # guarda a fração para não derivar
        mov = np.round(total)
        self._resto = total - mov
        return int(mov[0]), int(mov[1])

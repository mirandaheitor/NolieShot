"""Segue o seu personagem pela etiqueta de nome (bandeira + nome) embaixo do mobile.

Não é OCR: guarda a imagem da etiqueta uma vez (Num3 com o mouse em cima dela) e,
a cada quadro, procura essa imagem na tela com cv2.matchTemplate. A origem do tiro
fica a um deslocamento fixo da etiqueta (ajustado pela agulha no seu turno ou por Num7).
"""
from __future__ import annotations

import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


LARGURA_NOME = 64   # faixa à direita da bandeira onde fica o nome


def extrair_etiqueta(img: np.ndarray, cx: int, cy: int, larg: int = 80, alt: int = 8,
                     bandeira: np.ndarray | None = None):
    """Recorta a etiqueta (bandeira + nome) do jogador sob o cursor.
    Devolve (recorte RGB, (x, y) do canto = canto da bandeira) ou None.

    Com `bandeira`: acha a bandeira mais perto do cursor e recorta ela + LARGURA_NOME px
    à direita. Funciona com nome de qualquer cor (o azul some no céu/neve se for pela cor).
    Sem: pixels saturados agrupados por colunas (só funciona bem com nome laranja)."""
    if bandeira is not None:
        bh, bw = bandeira.shape[:2]
        x0, y0 = max(cx - 110, 0), max(cy - 20, 0)
        reg = np.ascontiguousarray(img[y0:cy + 20 + bh, x0:cx + 30 + bw])
        if reg.shape[0] >= bh and reg.shape[1] >= bw:
            res = cv2.matchTemplate(reg, bandeira, cv2.TM_CCOEFF_NORMED)
            ys, xs = np.nonzero(res >= 0.8)
            if len(xs):
                # a bandeira fica à ESQUERDA do nome: a mais perto do cursor
                i = int(np.argmin((x0 + xs + bw + LARGURA_NOME / 2 - cx) ** 2 + 4 * (y0 + ys + bh / 2 - cy) ** 2))
                fx, fy = x0 + int(xs[i]), y0 + int(ys[i])
                rec = img[fy:fy + bh, fx:fx + bw + LARGURA_NOME]
                if rec.shape[:2] == (bh, bw + LARGURA_NOME):
                    return rec.copy(), (fx, fy)
        return None
    x0, y0 = max(cx - larg, 0), max(cy - alt, 0)
    r = img[y0:cy + alt + 1, x0:cx + larg + 1].astype(int)
    if r.size == 0:
        return None
    # nome azul é pouco saturado (ex.: 136,176,216): limiar baixo para não ficar só a bandeira
    sat = (r.max(axis=2) - r.min(axis=2) >= 50) & (r.max(axis=2) >= 120)
    cols = np.nonzero(sat.any(axis=0))[0]
    if not len(cols):
        return None
    grupos = [[cols[0], cols[0]]]
    for c in cols[1:]:
        if c - grupos[-1][1] <= 6:
            grupos[-1][1] = c
        else:
            grupos.append([c, c])
    meio = cx - x0
    g0, g1 = min(grupos, key=lambda g: 0 if g[0] <= meio <= g[1] else min(abs(g[0] - meio), abs(g[1] - meio)))
    if g1 - g0 < 40:                      # só a bandeira (26 px) é igual em todo jogador BR: precisa do nome
        return None
    linhas = np.nonzero(sat[:, g0:g1 + 1].any(axis=1))[0]
    bx, by = x0 + g0 - 1, y0 + linhas[0] - 1
    rec = img[by:y0 + linhas[-1] + 2, bx:x0 + g1 + 2].copy()
    return rec, (int(bx), int(by))


class RastreioNome:
    def __init__(self, arquivo: Path, limiar: float = 0.8, margem: int = 80, excluir=(),
                 bandeira: Path | None = None):
        self.arquivo = Path(arquivo)
        self.limiar, self.margem = limiar, margem
        self.excluir = [tuple(r) for r in excluir]      # (x0, y0, x1, y1) onde o nome não conta
        self.bandeira = (np.asarray(Image.open(bandeira).convert("RGB"))
                         if bandeira is not None and Path(bandeira).exists() else None)
        self.modelo: np.ndarray | None = None
        self.pos: tuple[int, int] | None = None       # última posição achada (canto da etiqueta)
        self._ultima_busca_total = 0.0
        if self.arquivo.exists():
            modelo = np.asarray(Image.open(self.arquivo).convert("RGB"))
            # modelo antigo com só a bandeira (nome azul não entrava no recorte): bate com
            # qualquer jogador BR e com a lista de turnos. Ignora; refaça com Num3.
            if modelo.shape[1] >= 45:
                self.modelo = modelo
            else:
                print("rastreio: modelo do nome salvo só tem a bandeira; refaça com Num3")

    @property
    def ativo(self) -> bool:
        return self.modelo is not None

    def capturar(self, img: np.ndarray, cx: int, cy: int) -> bool:
        r = extrair_etiqueta(img, cx, cy, bandeira=self.bandeira)
        if r is None:
            return False
        self.modelo, self.pos = r
        self.arquivo.parent.mkdir(exist_ok=True)
        Image.fromarray(self.modelo).save(self.arquivo)
        return True

    def desligar(self) -> None:
        self.modelo, self.pos = None, None
        self.arquivo.unlink(missing_ok=True)

    def _buscar(self, img, x0, y0) -> tuple[float, tuple[int, int]] | None:
        h, w = self.modelo.shape[:2]
        if img.shape[0] < h or img.shape[1] < w:
            return None
        res = cv2.matchTemplate(img, self.modelo, cv2.TM_CCOEFF_NORMED)
        # a lista de turnos mostra a mesma bandeira + nome: não vale como posição no mapa
        for ex0, ey0, ex1, ey1 in self.excluir:
            res[max(ey0 - y0 - h, 0):max(ey1 - y0, 0), max(ex0 - x0 - w, 0):max(ex1 - x0, 0)] = -1
        _, score, _, (x, y) = cv2.minMaxLoc(res)
        return score, (x0 + x, y0 + y)

    def localizar(self, img: np.ndarray) -> tuple[int, int] | None:
        """Perto da última posição; se perdeu, a tela toda (no máximo 2x por segundo)."""
        if self.modelo is None:
            return None
        achou = None
        if self.pos is not None:
            h, w = self.modelo.shape[:2]
            x0, y0 = max(self.pos[0] - self.margem, 0), max(self.pos[1] - self.margem, 0)
            janela = img[y0:self.pos[1] + h + self.margem, x0:self.pos[0] + w + self.margem]
            achou = self._buscar(janela, x0, y0)
        if (achou is None or achou[0] < self.limiar) and time.time() - self._ultima_busca_total > 0.5:
            self._ultima_busca_total = time.time()
            achou = self._buscar(img, 0, 0)
        if achou is None or achou[0] < self.limiar:
            return None
        self.pos = achou[1]
        return self.pos

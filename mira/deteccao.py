"""Leitura do HUD por imagem.

* Dígitos (ângulo, força do vento): binariza a ROI, separa os caracteres por
  colunas vazias e compara cada um com templates aprendidos
  (ferramentas/calibrar_hud.py). O CMX fazia XOR de 6 pixels fixos por dígito,
  o que quebra com qualquer mudança de fonte/posição; com templates basta recalibrar.
* Seta do vento: pixels dentro de uma faixa de cor; a ponta é a massa de pixels
  mais distante do centro da ROI, do lado do centroide (a cabeça da seta pesa mais).
"""
from __future__ import annotations

import math
import re
from pathlib import Path

import numpy as np
from PIL import Image

TAMANHO = (10, 14)  # (largura, altura) normalizada de um caractere
NOMES = {"-": "menos"}
NOMES_INV = {v: k for k, v in NOMES.items()}


def recortar(img: np.ndarray, roi) -> np.ndarray | None:
    if not roi:
        return None
    x, y, w, h = (int(v) for v in roi)
    if w <= 0 or h <= 0 or y + h > img.shape[0] or x + w > img.shape[1] or x < 0 or y < 0:
        return None
    return img[y:y + h, x:x + w]


def binarizar(rgb: np.ndarray, limiar: int) -> np.ndarray:
    lum = rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114
    return lum > limiar


def segmentar(mascara: np.ndarray, min_pixels: int = 3) -> list[tuple[int, int, int, int]]:
    """Caixas (x0, x1, y0, y1) de cada caractere, separando por colunas vazias."""
    colunas = mascara.any(axis=0)
    caixas = []
    x = 0
    w = mascara.shape[1]
    while x < w:
        if not colunas[x]:
            x += 1
            continue
        x0 = x
        while x < w and colunas[x]:
            x += 1
        bloco = mascara[:, x0:x]
        if bloco.sum() >= min_pixels:
            linhas = np.nonzero(bloco.any(axis=1))[0]
            caixas.append((x0, x, int(linhas[0]), int(linhas[-1]) + 1))
    return caixas


def normalizar(mascara: np.ndarray) -> np.ndarray:
    img = Image.fromarray((mascara * 255).astype(np.uint8)).resize(TAMANHO, Image.BILINEAR)
    return np.asarray(img, dtype=float) / 255.0


def nome_arquivo_char(c: str) -> str:
    return NOMES.get(c, c)


class LeitorDigitos:
    def __init__(self, pasta: Path, score_min: float = 0.75):
        self.pasta = Path(pasta)
        self.score_min = score_min
        self.templates: list[tuple[str, np.ndarray]] = []
        self.recarregar()

    def recarregar(self) -> None:
        self.templates = []
        if not self.pasta.exists():
            return
        for arq in sorted(self.pasta.glob("*.png")):
            m = re.match(r"([^_]+)_", arq.name)
            if not m:
                continue
            c = NOMES_INV.get(m.group(1), m.group(1))
            mask = np.asarray(Image.open(arq).convert("L")) > 127
            self.templates.append((c, normalizar(mask)))

    @property
    def pronto(self) -> bool:
        return bool(self.templates)

    def ler(self, rgb: np.ndarray, limiar: int) -> tuple[str | None, float]:
        """Devolve (texto, pior score). texto=None se algum caractere não for reconhecido."""
        if not self.templates:
            return None, 0.0
        mask = binarizar(rgb, limiar)
        caixas = segmentar(mask)
        if not caixas:
            return None, 0.0
        texto, pior = "", 1.0
        for x0, x1, y0, y1 in caixas:
            v = normalizar(mask[y0:y1, x0:x1])
            c, s = max(((c, 1.0 - float(np.abs(v - t).mean())) for c, t in self.templates), key=lambda p: p[1])
            if s < self.score_min:
                return None, s
            texto += c
            pior = min(pior, s)
        return texto, pior

    def ler_int(self, rgb: np.ndarray, limiar: int) -> int | None:
        texto, _ = self.ler(rgb, limiar)
        if texto and re.fullmatch(r"-?\d+", texto):
            return int(texto)
        return None


#  Display de 7 segmentos (ângulo do HUD do Thor's Hammer)
#
#       a           Cada célula tem 6 px de largura e 10 de altura, com segmentos
#     f   b         de 2 px. Os segmentos apagados ficam visíveis em tom escuro,
#       g           então basta amostrar a luminância no meio de cada segmento.
#     e   c
#       d
_SEGMENTOS = {  # (dx, dy) do pixel amostrado a partir do canto superior esquerdo da célula
    "a": (2, 0), "b": (4, 2), "c": (4, 6), "d": (2, 8), "e": (0, 6), "f": (0, 2), "g": (2, 4),
}
_DIGITOS_7SEG = {
    "abcdef": 0, "bc": 1, "abdeg": 2, "abcdg": 3, "bcfg": 4, "acdfg": 5, "acdefg": 6, "cdefg": 6,
    "abc": 7, "abcf": 7, "abcdefg": 8, "abcdfg": 9, "abcfg": 9,
}


def _lum(rgb: np.ndarray, x: int, y: int) -> float:
    """Maior luminância num bloco 2x2: tolera traços de 1 px e erro de 1 px na posição."""
    bloco = rgb[y:y + 2, x:x + 2].reshape(-1, 3).astype(float)
    if bloco.size == 0:
        raise IndexError
    return float((bloco @ np.array([0.299, 0.587, 0.114])).max())


def _aceso(img, x0, y0, seg, lim, cor=None, tol_cor=16) -> bool:
    """seg = (dx, dy): bloco 2x2 no ponto. seg = [[dx, dy], ...]: TODOS os pixels exatos
    acesos (usado quando há desenho atrás dos dígitos, como a seta do vento).
    Com `cor`, aceso = pixel com a cor do dígito (± tol_cor por canal) em vez de claro:
    a seta atrás dos dígitos do vento é tão clara quanto eles, mas de outra cor."""
    if isinstance(seg[0], (list, tuple)):
        if cor is not None:
            alvo = np.array(cor, dtype=float)
            return all(float(np.abs(img[y0 + dy, x0 + dx].astype(float) - alvo).max()) <= tol_cor
                       for dx, dy in seg)
        pesos = np.array([0.299, 0.587, 0.114])
        return all(float(img[y0 + dy, x0 + dx].astype(float) @ pesos) > lim for dx, dy in seg)
    return _lum(img, x0 + seg[0], y0 + seg[1]) > lim


def _ler_celulas(img, celulas_x, y0, segmentos, lim, cor=None, tol_cor=16, um=None) -> str | None:
    """`um`: pontos de um '1' desenhado no MEIO da célula (fonte do mostrador do vento),
    que não acende nenhum dos 7 segmentos e seria lido como célula vazia."""
    texto = ""
    for x0 in celulas_x:
        acesos = "".join(s for s, seg in segmentos.items() if _aceso(img, x0, y0, seg, lim, cor, tol_cor))
        if not acesos:
            if um and _aceso(img, x0, y0, um, lim, cor, tol_cor):
                texto += "1"
            continue
        if acesos == "g" and not texto:   # só o traço do meio antes do número = sinal de menos
            texto = "-"
            continue
        if acesos not in _DIGITOS_7SEG:
            return None
        texto += str(_DIGITOS_7SEG[acesos])
    return texto or None


def _celulas_dinamicas(img: np.ndarray, cfg: dict, lim: float) -> list[int]:
    """Para números centralizados (vento): acha os blocos de colunas acesas na faixa
    dos dígitos e devolve o x da célula de cada um. Bloco estreito (o '1') é alinhado
    pela direita, porque só os segmentos b e c existem."""
    x_ini, x_fim = cfg["faixa_x"]
    y0, alt, larg = cfg["y_topo"], cfg["altura"], cfg["largura"]
    rgb = img[y0:y0 + alt, x_ini:x_fim].astype(float)
    faixa = rgb @ np.array([0.299, 0.587, 0.114])
    acesos = faixa > lim
    if "saturacao_max" in cfg:   # dígitos cinza: descarta o anel laranja do mostrador
        acesos &= (rgb.max(axis=2) - rgb.min(axis=2)) <= cfg["saturacao_max"]
    colunas = acesos.any(axis=0)
    celulas, x = [], 0
    while x < len(colunas):
        if not colunas[x]:
            x += 1
            continue
        ini = x
        while x < len(colunas) and colunas[x]:
            x += 1
        largura_bloco = x - ini
        celulas.append(x_ini + (ini if largura_bloco > larg // 2 else x - larg))
    return celulas


def ler_sete_segmentos(img: np.ndarray, cfg: dict) -> int | None:
    """Lê um número de um display de 7 segmentos em posições fixas.

    cfg (coordenadas da área cliente):
      "layouts":   [[x_célula, ...], ...]  tentados em ordem (ex.: 2 dígitos, depois 1 centralizado);
                   ou "celulas_x": [x, ...] para um layout só
      "y_topo":    y do topo das células
      "segmentos": {"a": [dx, dy], ...}    opcional, padrão = célula 6x10
      "menos":     [x, y] ou null         pixel do sinal de menos
      "um":        [[dx, dy], ...]        opcional: '1' centralizado na célula (todos acesos)
      "limiar":    luminância mínima de um segmento aceso
    Célula toda apagada = dígito em branco (ex.: dezena de '7')."""
    lim = cfg.get("limiar", 170)
    segmentos = {k: tuple(v) for k, v in cfg.get("segmentos", _SEGMENTOS).items()}
    if "faixa_x" in cfg:
        layouts = [_celulas_dinamicas(img, cfg, lim)]
    else:
        layouts = cfg.get("layouts") or [cfg["celulas_x"]]
    try:
        for celulas in layouts:
            texto = _ler_celulas(img, celulas, cfg["y_topo"], segmentos, lim,
                                 cfg.get("cor"), cfg.get("tol_cor", 16), cfg.get("um"))
            if texto is None:
                continue
            valor = int(texto)
            m = cfg.get("menos")
            if m and _lum(img, m[0], m[1]) > lim:
                valor = -valor
            return valor
    except (IndexError, ValueError):
        pass
    return None


def mascara_cor(rgb: np.ndarray, rgb_min, rgb_max) -> np.ndarray:
    lo = np.array(rgb_min).reshape(1, 1, 3)
    hi = np.array(rgb_max).reshape(1, 1, 3)
    return np.all((rgb >= lo) & (rgb <= hi), axis=2)


def ler_angulo_seta(rgb: np.ndarray, rgb_min, rgb_max, min_pixels: int = 6) -> float | None:
    """Ângulo (graus, convenção matemática) da seta dentro da ROI. A ROI deve
    estar centralizada no eixo de rotação da seta."""
    mask = mascara_cor(rgb, rgb_min, rgb_max)
    ys, xs = np.nonzero(mask)
    if len(xs) < min_pixels:
        return None
    cy, cx = (mask.shape[0] - 1) / 2, (mask.shape[1] - 1) / 2
    dx, dy = xs - cx, -(ys - cy)          # y para cima
    dist = np.hypot(dx, dy)
    longe = dist >= np.percentile(dist, 85)
    mx, my = dx.mean(), dy.mean()          # centroide: puxado para a cabeça da seta
    if math.hypot(mx, my) > 0.5:
        lado = (dx * mx + dy * my) > 0
        sel = longe & lado
        if sel.any():
            longe = sel
    return math.degrees(math.atan2(dy[longe].mean(), dx[longe].mean())) % 360

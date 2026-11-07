"""Diferenças entre T1, T2 e SS por mobile — porte de TShMatrix::fillXxx()
(Plugins/Aimbot/subplugin/mobiles.cpp do CMX).

O CMX não muda a física por tipo de tiro: parte da mesma trajetória base e
  * adiciona projéteis extras com pequenos desvios de ângulo/força (BigFoot, Grub, Frank);
  * marca pontos no caminho (onde o SS do Armor/Turtle ativa, as quebras do T2 do Mage/Turtle);
  * desenha os repolhos girando em volta do tiro principal (T2 do Trico).

Os "passos" aqui são índices da lista de pontos de fisica.simular(): o ponto k é a
posição depois de k passos. No CMX isso aparecia como `tempo = 5·k`.

SS com trajetória própria (fillMaya / fillPhoenix / fillWolf): o maxado da Maya volta,
o Phoenix desacelera, sobe e mergulha, o Wolf marca 5 pontos e depois mergulha.
O Kalsiddon marca o ponto de mudança (depende da força) em qualquer tiro.
Nak, Raon, o T1/T2 do Phoenix e o T2 da Maya ainda não foram portados. O Boomer
não tem SS no CMX (o código estava comentado).

Esses desenhos são só visuais: a força sugerida continua vindo da trajetória comum.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .fisica import PASSOS_MAX, TICK, Limites, Vento, angulo_absoluto, parametros, simular, vento_quantizado
from .mobiles import Mobile

T1, T2, SS = 0, 1, 2
NOMES_TIRO = {T1: "T1", T2: "T2", SS: "SS"}


@dataclass(frozen=True)
class Padrao:
    # (desvio de ângulo em graus, desvio de força) de cada projétil extra.
    # Se não houver nenhum (0, 0), o tiro principal também é desenhado.
    subs: tuple[tuple[float, float], ...] = ()
    marcas: tuple[int, ...] = ()          # passos onde marcar um ponto
    trico: bool = False                   # repolhos girando (T2 do Trico)


def _passos_mage() -> tuple[int, ...]:
    """T2 do Mage: no CMX `tempo` zera a cada marca e a próxima vem quando
    tempo − 5 == magePoints[i], ou seja, (magePoints[i] + 5) / 5 passos depois."""
    mage_points = [15, 40, 45, 50, 45, 45, 45, 45, 45, 45, 50, 45, 45, 45, 50, 45, 45, 50, 45, 45,
                   45, 50, 45, 40, 50, 45, 45, 45, 45, 45, 45, 45, 45, 45, 45, 45, 45, 45, 45, 45]
    passos, k = [], 0
    for mp in mage_points:
        k += (mp + 5) // 5
        passos.append(k)
    return tuple(passos)


PADROES: dict[tuple[str, int], Padrao] = {
    ("Armor", SS): Padrao(marcas=(81,)),
    ("Turtle", T2): Padrao(marcas=(23, 33, 44, 55, 69, 86, 121)),
    ("Turtle", SS): Padrao(marcas=(97,)),
    ("Mage", T2): Padrao(marcas=_passos_mage()),
    ("BigFoot", T1): Padrao(subs=((-1, 5.6), (1, 5.4), (0, 15.4), (0, -3.9))),
    ("BigFoot", T2): Padrao(subs=((-1, -9), (-1, 5), (-1, 20), (1, -9), (1, 5), (1, 20))),
    ("BigFoot", SS): Padrao(subs=((0, 14), (0, -4), (-1, 4), (1, 5))),
    ("Grub", T2): Padrao(subs=((-2.1, -9.8), (-1.1, -5.8), (-0.1, -1.8), (0.9, 1.6))),
    ("Frank", SS): Padrao(subs=tuple((-10.0 * i, 0.0) for i in range(5))),
    ("Trico", T2): Padrao(trico=True),
}


def padrao(mobile: Mobile, tiro: int) -> Padrao:
    return PADROES.get((mobile.nome, tiro), Padrao())


@dataclass
class Desenho:
    principal: list = field(default_factory=list)      # pontos da trajetória base (vazia se não é desenhada)
    extras: list = field(default_factory=list)          # listas de pontos dos projéteis extras / repolhos
    marcas: list = field(default_factory=list)          # pontos a marcar


def _repolhos(base: list, direita: bool, raio: float = 43.0, inicio: int = 21):
    """T2 do Trico (fillTrico): dois repolhos giram em volta do tiro principal.
    Até o passo `inicio` o CMX liga a origem à posição do repolho com uma reta."""
    vel = 7.0 if direita else -7.3
    fase = 172 if direita else -55
    r1, r2 = [], []
    for k in range(1, len(base)):
        t = (k - 1) * 0.05
        a1 = fase + (180 if direita else 0) + int(vel * t * 10)
        a2 = fase + (0 if direita else 180) + int(vel * t * 10)
        bx, by = base[k]
        if k >= inicio:
            r1.append((bx + int(raio * math.cos(math.radians(a1))), by + int(raio * math.sin(math.radians(a1)))))
            r2.append((bx + int(raio * math.cos(math.radians(a2))), by + int(raio * math.sin(math.radians(a2)))))
    if r1:
        r1.insert(0, base[0])
        r2.insert(0, base[0])
    return [r1, r2]


class _Passo:
    """Integrador passo a passo (o mesmo de fisica.simular), para os SS que mudam a
    física no meio do caminho."""

    def __init__(self, angulo_abs, forca, origem, vento, mobile, direita):
        alfa, beta, self.g = (float(v) for v in parametros(angulo_abs, mobile.gravidade, mobile.grub, direita))
        qx, qy = vento_quantizado(vento)
        self.ax, self.ay = qx * mobile.efeito, qy * mobile.efeito
        self.vx, self.vy = alfa * forca, beta * forca
        self.x, self.y = map(float, origem)
        self.usx = self.usy = 0.0

    def ida(self):
        m = TICK * TICK * 0.5
        self.x += self.vx * TICK + self.usx + self.ax * m
        self.y -= self.vy * TICK + self.usy + (self.ay - self.g) * m
        self.usx += self.ax * TICK
        self.usy += (self.ay - self.g) * TICK
        return self.x, self.y


def _fora(p, lim: Limites) -> bool:
    return not (lim.x_min <= p[0] <= lim.x_max and lim.y_min <= p[1] <= lim.y_max)


def _maya_ss(angulo_hud, direita, forca, base) -> Desenho | None:
    """fillMaya, tiro 2: no "pico" o maxado volta para a mão da Maya. A volta do CMX é
    a mesma integração com os sinais trocados e velocidade acumulada zerada, ou seja,
    pico − (deslocamento da ida): chega exatamente na origem depois de k passos."""
    ang = int(angulo_absoluto(angulo_hud, direita))
    ang_tiro = abs((ang % 90) - 45)
    parte = (math.cos(math.radians(ang_tiro)) - 0.008) * 100 - (96 - int(forca) * 0.24)
    k = int(parte)                                   # pico = 5·k no "tempo" do CMX
    if k <= 0 or k >= len(base):
        return None
    (px, py), (ox, oy) = base[k], base[0]
    volta = [(px - (x - ox), py - (y - oy)) for x, y in base[1:k + 1]]
    return Desenho(principal=base[:k + 1] + volta, marcas=[(px, py)])


# fillPhoenix, tiro 2: (raio, fase2, tempo, tempo2) a cada 10° e o raio do giro pela força
_PHOENIX_SS = ((0, 258, 80, 27), (0, 257, 80, 27), (0, 256, 80, 27), (0, 255, 80, 27), (0, 254, 80, 27),
               (0.7, 253, 90, 28), (1.5, 253, 80, 28), (2, 252, 80, 28), (1, 252, 80, 28), (1, 252, 60, 28))
_RAIOS_SS = (0, 0, 0.33, 0.67, 1)


def _phoenix_ss(angulo_hud, direita, forca, origem, vento, mobile, lim: Limites) -> Desenho:
    ang = int(angulo_absoluto(angulo_hud, direita))
    quad = 90 if ang == 90 else ang % 90
    quad = 90 - quad if ang > 90 else quad
    mod, i1 = quad % 10, quad // 10
    i2 = i1 if i1 + 1 > 9 else i1 + 1
    raio, fase2, tempo, tempo2 = (a + (b - a) / 10 * mod for a, b in zip(_PHOENIX_SS[i1], _PHOENIX_SS[i2]))
    f = int(forca)
    mod_f, f1 = f % 100, min(f // 100, 4)
    f2 = f1 if f1 + 1 > 4 else f1 + 1
    raio_tiro = raio * (_RAIOS_SS[f1] + (_RAIOS_SS[f2] - _RAIOS_SS[f1]) / 100 * mod_f)
    fase2 += 8 - f * 0.02

    s = _Passo(angulo_absoluto(angulo_hud, direita), forca, origem, vento, mobile, direita)
    pts = [(s.x, s.y)]
    for _ in range(42):                              # tempo 210: muda o comportamento
        pts.append(s.ida())
        if _fora(pts[-1], lim):
            return Desenho(principal=pts)
    marca = pts[-1]
    dif = s.x - origem[0]
    inverte = (direita and dif <= -2) or (not direita and dif >= 2)

    m = TICK * TICK * 0.5                            # desacelera: aceleração com sinal trocado
    for _ in range(int(tempo2)):
        s.x += s.vx * TICK + (s.usx + s.ax * m)
        s.y -= s.vy * TICK + s.usy + (s.ay - s.g) * m
        s.usx -= s.ax * TICK
        s.usy -= (s.ay - s.g) * TICK
        pts.append((s.x, s.y))

    x, y = s.x, s.y - int(tempo - (40 - 0.1 * f))    # sobe
    pts.append((x, y))
    sinal = (-1 if direita else 1) * (-1 if inverte else 1)
    for i in range(0, 160, 5):                       # giro pequeno
        x += raio_tiro * math.cos(math.radians(i - 90)) * sinal
        y += raio_tiro * math.sin(math.radians(i - 90))
        pts.append((x, y))
    i = 0.0
    while i < 160:                                   # mergulho (passos de 80 px)
        x -= 80 * math.cos(math.radians(i + fase2)) * sinal
        y -= 80 * math.sin(math.radians(i + fase2))
        pts.append((x, y))
        if _fora((x, y), lim):
            break
        i += 0.5
    return Desenho(principal=pts, marcas=[marca])


def _wolf_ss(angulo_hud, direita, forca, origem, vento, mobile, lim: Limites, chao_y: float) -> Desenho:
    """fillWolf, tiro 2: marcas nos passos 32, 48, 64, 80 e 96 com uma linha até o chão;
    a partir do passo 120 a gravidade cresce 5.8 por passo (o tiro mergulha)."""
    s = _Passo(angulo_absoluto(angulo_hud, direita), forca, origem, vento, mobile, direita)
    d = Desenho(principal=[(s.x, s.y)])
    mergulho = False
    for k in range(1, PASSOS_MAX + 1):
        if mergulho:
            s.g += 5.8
        p = s.ida()
        d.principal.append(p)
        if k in (32, 48, 64, 80, 96) and p[1] <= chao_y:
            d.marcas.append(p)
            d.extras.append([p, (p[0], chao_y)])
        if k == 120:
            mergulho = True
        if _fora(p, lim):
            break
    return d


def _passo_kalsiddon(forca) -> int:
    """fillKalsiddon: semiTempo = 0.8·força arredondado para baixo em múltiplo de 5, + 25."""
    t = int(0.8 * forca)
    return (t - (t % 5 - 25)) // 5


def desenhar_tiro(tiro: int, mobile: Mobile, angulo_hud: float, direita: bool, forca: float,
                  origem, vento: Vento, limites: Limites = Limites(), chao_y: float = 515) -> Desenho:
    p = padrao(mobile, tiro)
    if tiro == SS and mobile.nome == "Phoenix":
        return _phoenix_ss(angulo_hud, direita, forca, origem, vento, mobile, limites)
    if tiro == SS and mobile.nome == "Wolf":
        return _wolf_ss(angulo_hud, direita, forca, origem, vento, mobile, limites, chao_y)
    base = simular(angulo_absoluto(angulo_hud, direita), forca, origem, vento, mobile, direita, limites)
    if tiro == SS and mobile.nome == "Maya":
        d = _maya_ss(angulo_hud, direita, forca, base)
        if d is not None:
            return d
    d = Desenho()
    if not p.subs or any(da == 0 and df == 0 for da, df in p.subs):
        d.principal = base
    for da, df in p.subs:
        if da == 0 and df == 0:
            continue
        # O CMX somava o desvio ao ângulo ABSOLUTO, o que espelha errado para quem está
        # virado à esquerda; aqui o desvio é aplicado à elevação (ângulo do HUD).
        d.extras.append(simular(angulo_absoluto(angulo_hud + da, direita), forca + df, origem, vento,
                                mobile, direita, limites))
    if p.trico:
        d.extras += _repolhos(base, direita)
    passos = list(p.marcas)
    if mobile.nome == "Kalsiddon":
        passos.append(_passo_kalsiddon(forca))
    d.marcas = [base[k] for k in passos if 0 < k < len(base)]
    return d


def ler_tipo_tiro(img: np.ndarray, cfg: dict) -> int | None:
    """Botão selecionado (1, 2, SS): LED verde aceso em cima dele ou, com "r_menos_b"
    no cfg, o próprio botão pintado de amarelo (os outros ficam claros/pálidos).

    cfg["ss"] = {"ponto", "cor_normal", "dif_min"}: quando só os botões 1 e 2 estão em
    "leds", o SS conta como selecionado se nenhum dos dois estiver aceso E o botão SS
    estiver com cor diferente da normal (sem isso, fora do turno, mantém o anterior)."""
    acesos = []
    for i, (x, y) in enumerate(cfg["leds"]):
        bloco = img[y - 1:y + 2, x - 3:x + 4].reshape(-1, 3).astype(int)
        if len(bloco) == 0:
            return None
        r, g, b = bloco[:, 0].mean(), bloco[:, 1].mean(), bloco[:, 2].mean()
        if "r_menos_b" in cfg:
            if r - b >= cfg["r_menos_b"]:
                acesos.append(i)
        elif g >= cfg.get("g_min", 150) and g - r >= cfg.get("g_menos_r", 60):
            acesos.append(i)
    if not acesos and "ss" in cfg:
        x, y = cfg["ss"]["ponto"]
        bloco = img[y - 1:y + 2, x - 3:x + 4].reshape(-1, 3).astype(float)
        if len(bloco) and np.abs(bloco.mean(axis=0) - np.array(cfg["ss"]["cor_normal"])).max() >= cfg["ss"].get("dif_min", 40):
            return SS
    return acesos[0] if len(acesos) == 1 else None

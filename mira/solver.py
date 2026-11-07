"""Busca de força (e ângulo) que leva o projétil até o alvo.

O original (TCalculador::calcularMelhor) fazia busca grossa de 20 em 20 e depois
refinava ±20 de 1 em 1, o que pode cair num mínimo local. Aqui todas as forças
0..força_max são simuladas de uma vez (numpy), então o resultado é o ótimo global
da grade inteira.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .fisica import Limites, Vento, angulo_absoluto, parametros, varrer, vento_quantizado
from .mobiles import Mobile


@dataclass(frozen=True)
class Solucao:
    angulo_hud: int
    forca: int
    erro: float                  # px entre o alvo e o ponto mais próximo da curva
    ponto: tuple[float, float]   # ponto da curva mais próximo do alvo


def _grade(angulos_hud: np.ndarray, forca_max: int, origem, alvo, vento: Vento,
           mobile: Mobile, direita: bool, limites: Limites):
    ang_abs = np.array([angulo_absoluto(a, direita) for a in angulos_hud], dtype=float)[:, None]
    forcas = np.arange(forca_max + 1, dtype=float)[None, :]
    alfa, beta, g = parametros(ang_abs, mobile.gravidade, mobile.grub, direita)
    qx, qy = vento_quantizado(vento)
    return varrer(alfa, beta, g, qx * mobile.efeito, qy * mobile.efeito, forcas, origem, alvo, limites)


def melhor_forca(angulo_hud: int, origem, alvo, vento: Vento, mobile: Mobile, direita: bool,
                 forca_max: int = 400, limites: Limites = Limites()) -> Solucao:
    d, px, py = _grade(np.array([angulo_hud]), forca_max, origem, alvo, vento, mobile, direita, limites)
    f = int(np.argmin(d[0]))
    return Solucao(int(angulo_hud), f, float(d[0, f]), (float(px[0, f]), float(py[0, f])))


def melhores_angulos(origem, alvo, vento: Vento, mobile: Mobile, direita: bool,
                     angulos=range(0, 91), forca_max: int = 400, tolerancia: float = 4.0,
                     n: int = 5, separacao: int = 5, limites: Limites = Limites()) -> list[Solucao]:
    """Para cada ângulo acha a melhor força; devolve até `n` opções que acertam
    (erro <= tolerância) com MENOR força — tiros mais fracos sofrem menos com o vento —
    separadas por pelo menos `separacao` graus. Se nenhuma acerta, as de menor erro."""
    angs = np.array(list(angulos))
    d, px, py = _grade(angs, forca_max, origem, alvo, vento, mobile, direita, limites)
    f = np.argmin(d, axis=1)
    linhas = np.arange(len(angs))
    sols = [Solucao(int(angs[i]), int(f[i]), float(d[i, f[i]]), (float(px[i, f[i]]), float(py[i, f[i]])))
            for i in linhas]
    acertos = [s for s in sols if s.erro <= tolerancia]
    ordem = sorted(acertos, key=lambda s: (s.forca, s.erro)) if acertos else sorted(sols, key=lambda s: s.erro)
    escolhidas: list[Solucao] = []
    for s in ordem:
        if all(abs(s.angulo_hud - e.angulo_hud) >= separacao for e in escolhidas):
            escolhidas.append(s)
            if len(escolhidas) == n:
                break
    return escolhidas

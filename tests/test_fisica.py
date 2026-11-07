import math
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mira.fisica import Vento, angulo_absoluto, parametros, simular, varrer, vento_quantizado  # noqa: E402
from mira.mobiles import MOBILES, indice_por_nome  # noqa: E402
from mira.solver import melhor_forca, melhores_angulos  # noqa: E402

ARMOR = MOBILES[indice_por_nome("Armor")]
GRUB = MOBILES[indice_por_nome("Grub")]
ORIGEM = (200.0, 400.0)


def dist_segmentos(pontos, alvo):
    tx, ty = alvo
    melhor = math.hypot(pontos[0][0] - tx, pontos[0][1] - ty)
    for (x0, y0), (x1, y1) in zip(pontos, pontos[1:]):
        dx, dy = x1 - x0, y1 - y0
        l2 = dx * dx + dy * dy or 1.0
        t = min(1.0, max(0.0, ((tx - x0) * dx + (ty - y0) * dy) / l2))
        melhor = min(melhor, math.hypot(x0 + t * dx - tx, y0 + t * dy - ty))
    return melhor


class TestFisica(unittest.TestCase):
    def test_angulo_absoluto(self):
        self.assertEqual(angulo_absoluto(45, True), 45)
        self.assertEqual(angulo_absoluto(45, False), 135)
        self.assertEqual(angulo_absoluto(-10, True), 350)

    def test_vento_quantizado_trunca_como_c(self):
        self.assertEqual(vento_quantizado(Vento(10, 0)), (10, 0))
        self.assertEqual(vento_quantizado(Vento(10, 180)), (-10, 0))
        self.assertEqual(vento_quantizado(Vento(10, 45)), (7, 7))   # 7.07 -> 7
        self.assertEqual(vento_quantizado(Vento(10, 225)), (-7, -7))

    def test_sobe_e_desce(self):
        pts = simular(60, 250, ORIGEM, Vento(), ARMOR, True)
        ys = [p[1] for p in pts]
        self.assertLess(min(ys), ORIGEM[1] - 50)      # subiu (y menor = mais alto)
        self.assertGreater(ys[-1], ORIGEM[1])          # e caiu abaixo da origem
        self.assertGreater(pts[-1][0], ORIGEM[0])      # foi para a direita

    def test_espelho_esquerda_direita(self):
        d = simular(angulo_absoluto(50, True), 220, ORIGEM, Vento(), ARMOR, True)
        e = simular(angulo_absoluto(50, False), 220, ORIGEM, Vento(), ARMOR, False)
        # os limites não são simétricos em torno da origem, então compara o trecho comum
        self.assertGreater(min(len(d), len(e)), 100)
        for (xd, yd), (xe, ye) in zip(d, e):
            self.assertAlmostEqual(xd - ORIGEM[0], -(xe - ORIGEM[0]), places=6)
            self.assertAlmostEqual(yd, ye, places=6)

    def test_vento_a_favor_vai_mais_longe(self):
        sem = simular(45, 200, ORIGEM, Vento(), ARMOR, True)
        com = simular(45, 200, ORIGEM, Vento(20, 0), ARMOR, True)
        alvo_y = ORIGEM[1]
        def alcance(pts):
            for (x0, y0), (x1, y1) in zip(pts[10:], pts[11:]):
                if y0 <= alvo_y < y1:
                    return x1
        self.assertGreater(alcance(com), alcance(sem))

    def test_varrer_igual_ao_escalar(self):
        alvo = (640.0, 380.0)
        for mob in (ARMOR, GRUB):
            for ang, forca, vento in [(45, 180, Vento()), (70, 300, Vento(15, 120)), (130, 260, Vento(8, 300))]:
                direita = ang < 90
                pts = simular(ang, forca, ORIGEM, vento, mob, direita)
                alfa, beta, g = parametros(ang, mob.gravidade, mob.grub, direita)
                qx, qy = vento_quantizado(vento)
                d, _, _ = varrer(alfa, beta, g, qx * mob.efeito, qy * mob.efeito, forca, ORIGEM, alvo)
                self.assertAlmostEqual(float(d), dist_segmentos(pts, alvo), places=6)


class TestSolver(unittest.TestCase):
    def _alvo_de(self, ang_hud, forca, vento, mob, direita, origem=ORIGEM):
        pts = simular(angulo_absoluto(ang_hud, direita), forca, origem, vento, mob, direita)
        # pega um ponto já na descida, abaixo da altura da origem
        for p in pts:
            if p[1] > origem[1] + 30:
                return p
        self.fail("trajetória não desceu")

    def test_recupera_forca(self):
        casos = [(45, 237, Vento(), True), (60, 311, Vento(12, 90), False), (30, 150, Vento(25, 200), True)]
        for ang, forca, vento, direita in casos:
            origem = ORIGEM if direita else (1600.0, 400.0)
            alvo = self._alvo_de(ang, forca, vento, ARMOR, direita, origem)
            s = melhor_forca(ang, origem, alvo, vento, ARMOR, direita)
            self.assertLessEqual(abs(s.forca - forca), 1, (ang, forca, vento, s))
            self.assertLess(s.erro, 2.0)

    def test_melhores_angulos_acertam(self):
        alvo = self._alvo_de(50, 260, Vento(10, 45), ARMOR, True)
        sols = melhores_angulos(ORIGEM, alvo, Vento(10, 45), ARMOR, True)
        self.assertTrue(sols)
        self.assertTrue(all(s.erro <= 4.0 for s in sols))
        forcas = [s.forca for s in sols]
        self.assertEqual(forcas, sorted(forcas))


if __name__ == "__main__":
    unittest.main()

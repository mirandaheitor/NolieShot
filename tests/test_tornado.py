"""Tornado (porte de TShMatrix::calculaTornado do CMX)."""
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from mira.fisica import Limites, Vento, angulo_absoluto, passar_tornado, simular  # noqa: E402
from mira.mobiles import MOBILES, indice_por_nome  # noqa: E402
from mira.solver import melhor_forca  # noqa: E402

ARMOR = MOBILES[indice_por_nome("Armor")]


class TestTornado(unittest.TestCase):
    def test_tres_voltas_seguindo_a_inclinacao(self):
        # indo para a direita e subindo 1 px a cada 2 px (y da tela diminui)
        pts, saida = passar_tornado(90, 100, 110, 90, 100, 140)
        self.assertEqual(pts, [(100, 95.0), (140, 75.0), (100, 55.0), (140, 35.0)])
        self.assertEqual(saida, (140, 35.0))

    def test_vindo_da_direita(self):
        pts, saida = passar_tornado(150, 100, 130, 110, 100, 140)   # para a esquerda, descendo
        self.assertEqual(pts[0], (140, 105.0))
        self.assertEqual(saida, (100, 165.0))                        # 3 × 0.5 × 40 = 60 a mais

    def test_so_dispara_ao_entrar(self):
        self.assertIsNone(passar_tornado(110, 100, 120, 90, 100, 140))   # já estava dentro
        self.assertIsNone(passar_tornado(50, 100, 60, 90, 100, 140))     # nem chegou

    def test_trajetoria_e_solver_concordam(self):
        lim = Limites(tornados=((400, 440),))
        origem, ang, f = (100, 400), 45, 220
        pts = simular(angulo_absoluto(ang, True), f, origem, Vento(), ARMOR, True, lim)
        sem = simular(angulo_absoluto(ang, True), f, origem, Vento(), ARMOR, True, Limites())
        self.assertNotEqual(pts[-1], sem[-1])                       # o tornado mudou o tiro
        alvo = next(p for p in pts if p[0] > 600)                   # um ponto depois do tornado
        sol = melhor_forca(ang, origem, alvo, Vento(), ARMOR, True, 400, lim)
        self.assertEqual(sol.forca, f)
        self.assertLess(sol.erro, 1.0)


if __name__ == "__main__":
    unittest.main()

"""SS portados do CMX (fillMaya / fillPhoenix / fillWolf / fillKalsiddon) e detecção do SS."""
import math
import sys
import unittest
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from mira.fisica import Vento  # noqa: E402
from mira.mobiles import MOBILES, indice_por_nome  # noqa: E402
from mira.tiros import SS, T1, T2, _passo_kalsiddon, desenhar_tiro, ler_tipo_tiro  # noqa: E402


def mob(nome):
    return MOBILES[indice_por_nome(nome)]


class TestSS(unittest.TestCase):
    def test_maya_volta_para_a_origem(self):
        for vento in (Vento(0, 0), Vento(12, 135)):
            d = desenhar_tiro(SS, mob("Maya"), 45, True, 200, (100, 300), vento)
            self.assertEqual(len(d.marcas), 1)
            fim = d.principal[-1]
            self.assertLess(math.hypot(fim[0] - 100, fim[1] - 300), 1e-6)

    def test_maya_t1_continua_normal(self):
        d = desenhar_tiro(T1, mob("Maya"), 45, True, 200, (100, 300), Vento())
        self.assertEqual(d.marcas, [])

    def test_phoenix_ss_marca_no_passo_42_e_mergulha(self):
        d = desenhar_tiro(SS, mob("Phoenix"), 45, True, 250, (100, 300), Vento())
        base = desenhar_tiro(T1, mob("Phoenix"), 45, True, 250, (100, 300), Vento()).principal
        self.assertEqual(d.marcas, [base[42]])
        self.assertGreater(d.principal[-1][1], 300)          # termina descendo

    def test_wolf_ss_marcas_com_linha_ate_o_chao(self):
        d = desenhar_tiro(SS, mob("Wolf"), 50, True, 260, (100, 300), Vento(), chao_y=515)
        self.assertEqual(len(d.marcas), len(d.extras))
        self.assertTrue(d.marcas)
        for (x, y), linha in zip(d.marcas, d.extras):
            self.assertEqual(linha, [(x, y), (x, 515)])

    def test_kalsiddon(self):
        self.assertEqual(_passo_kalsiddon(250), 45)           # int(200) - (0 - 25) = 225 -> 45 passos
        self.assertEqual(_passo_kalsiddon(253), 45)           # int(202.4)=202 -> 200+25 = 225
        d = desenhar_tiro(T2, mob("Kalsiddon"), 45, True, 250, (100, 300), Vento())
        self.assertEqual(len(d.marcas), 1)

    def test_detecta_ss(self):
        cfg = {"leds": [[10, 10], [30, 10]], "r_menos_b": 70,
               "ss": {"ponto": [50, 10], "cor_normal": [205, 88, 56], "dif_min": 40}}
        img = np.zeros((20, 60, 3), np.uint8)
        img[:, :] = (203, 203, 162)                          # 1 e 2 pálidos
        img[8:13, 46:55] = (205, 88, 56)                     # SS na cor normal
        self.assertIsNone(ler_tipo_tiro(img, cfg))           # nada selecionado: mantém o anterior
        img[8:13, 46:55] = (250, 200, 60)                    # SS mudou de cor
        self.assertEqual(ler_tipo_tiro(img, cfg), SS)
        img[8:13, 6:15] = (171, 144, 73)                     # botão 1 amarelo
        self.assertEqual(ler_tipo_tiro(img, cfg), T1)


if __name__ == "__main__":
    unittest.main()

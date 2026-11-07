import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mira.fisica import Vento, angulo_absoluto, simular  # noqa: E402
from mira.mobiles import MOBILES, indice_por_nome  # noqa: E402
from mira.tiros import SS, T1, T2, desenhar_tiro  # noqa: E402

O = (300.0, 400.0)


def mob(nome):
    return MOBILES[indice_por_nome(nome)]


class TestTiros(unittest.TestCase):
    def test_sem_padrao_e_so_a_base(self):
        d = desenhar_tiro(T1, mob("Armor"), 50, True, 200, O, Vento())
        self.assertEqual(d.principal, simular(angulo_absoluto(50, True), 200, O, Vento(), mob("Armor"), True))
        self.assertEqual((d.extras, d.marcas), ([], []))

    def test_armor_ss_marca_passo_81(self):
        d = desenhar_tiro(SS, mob("Armor"), 60, True, 300, O, Vento())
        self.assertEqual(d.marcas, [d.principal[81]])

    def test_bigfoot_quantidades(self):
        for tiro, n in ((T1, 4), (T2, 6), (SS, 4)):
            d = desenhar_tiro(tiro, mob("BigFoot"), 45, True, 200, O, Vento())
            self.assertEqual(len(d.extras), n)
            self.assertEqual(d.principal, [])     # nenhum sub com desvio (0, 0)

    def test_frank_ss_leque_espelhado(self):
        d = desenhar_tiro(SS, mob("Frank"), 60, True, 250, O, Vento())
        e = desenhar_tiro(SS, mob("Frank"), 60, False, 250, O, Vento())
        self.assertTrue(d.principal)
        self.assertEqual(len(d.extras), 4)
        for cd, ce in zip(d.extras, e.extras):
            for (xd, yd), (xe, ye) in list(zip(cd, ce))[:50]:
                self.assertAlmostEqual(xd - O[0], -(xe - O[0]), places=6)
                self.assertAlmostEqual(yd, ye, places=6)

    def test_trico_t2_repolhos(self):
        d = desenhar_tiro(T2, mob("Trico"), 50, True, 250, O, Vento())
        self.assertEqual(len(d.extras), 2)
        for r in d.extras:
            self.assertEqual(r[0], O)               # reta saindo da origem
            bx, by = d.principal[21]
            x, y = r[1]
            self.assertAlmostEqual(((x - bx) ** 2 + (y - by) ** 2) ** 0.5, 43, delta=1.5)

    def test_mage_t2_primeira_marca(self):
        d = desenhar_tiro(T2, mob("Mage"), 50, True, 300, O, Vento())
        self.assertEqual(d.marcas[0], d.principal[4])
        self.assertEqual(d.marcas[1], d.principal[13])


if __name__ == "__main__":
    unittest.main()

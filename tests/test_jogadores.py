"""Etiquetas de nome no mapa (bandeira + nome) e o time pela cor do nome."""
import sys
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from mira.jogadores import Jogadores, mais_perto  # noqa: E402


class TestJogadores(unittest.TestCase):
    def test_acha_os_dois_times(self):
        img = np.asarray(Image.open(RAIZ / "tests" / "fixtures" / "jogadores.png").convert("RGB"))
        j = Jogadores(RAIZ / "templates" / "bandeira.png")
        achadas = {(e.x, e.y): e.time for e in j.achar(img)}
        self.assertEqual(achadas, {(73, 57): "azul", (242, 101): "laranja"})   # BigJake e NolieCps

    def test_exclui_regiao(self):
        img = np.asarray(Image.open(RAIZ / "tests" / "fixtures" / "jogadores.png").convert("RGB"))
        j = Jogadores(RAIZ / "templates" / "bandeira.png", excluir=[[0, 0, 150, 170]])
        self.assertEqual([(e.x, e.y) for e in j.achar(img)], [(242, 101)])

    def test_mais_perto(self):
        img = np.asarray(Image.open(RAIZ / "tests" / "fixtures" / "jogadores.png").convert("RGB"))
        etqs = Jogadores(RAIZ / "templates" / "bandeira.png").achar(img)
        self.assertEqual(mais_perto(etqs, (80, 60)).time, "azul")
        self.assertIsNone(mais_perto(etqs, (500, 500), raio=50))


if __name__ == "__main__":
    unittest.main()

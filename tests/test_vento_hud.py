"""Regressão com recortes reais do HUD.

* vento_*.png: mostrador de vento da barra ANTIGA (Thor's Hammer, x 370..430, y 40..100),
  lido com config_hud_antigo.json.
* barra_*.png: barra PADRÃO (x 180..340, y 515..600), lida com o config.json atual:
  ângulo no círculo preto, vento no centro do mostrador e botão de tiro selecionado.
"""
import json
import re
import sys
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from mira import config as C  # noqa: E402
from mira.deteccao import ler_sete_segmentos  # noqa: E402
from mira.tiros import ler_tipo_tiro  # noqa: E402

FIXTURES = RAIZ / "tests" / "fixtures"


class TestVentoHUD(unittest.TestCase):
    def test_barra_antiga(self):
        cfg = json.loads((RAIZ / "config_hud_antigo.json").read_text(encoding="utf-8"))["vento_7seg"]
        for arq in sorted(FIXTURES.glob("vento_*.png")):
            esperado = int(arq.stem.split("_")[1])
            tela = np.zeros((600, 800, 3), np.uint8)
            tela[40:100, 370:430] = np.asarray(Image.open(arq).convert("RGB"))
            self.assertEqual(ler_sete_segmentos(tela, cfg), esperado, arq.name)

    def test_barra_padrao(self):
        cfg = C.carregar()
        arqs = sorted(FIXTURES.glob("barra_*.png"))
        self.assertTrue(arqs)
        for arq in arqs:
            ang, vento, tiro = (int(v) for v in re.fullmatch(r"barra_ang(-?\d+)_vento(\d+)_tiro(\d)", arq.stem).groups())
            tela = np.zeros((600, 800, 3), np.uint8)
            tela[515:600, 180:340] = np.asarray(Image.open(arq).convert("RGB"))
            self.assertEqual(ler_sete_segmentos(tela, cfg["angulo_7seg"]), ang, arq.name)
            self.assertEqual(ler_sete_segmentos(tela, cfg["vento_7seg"]), vento, arq.name)
            self.assertEqual(ler_tipo_tiro(tela, cfg["tipo_tiro"]), tiro, arq.name)

    def test_mostrador_so_vento(self):
        """mostrador_vento<N>.png: só o mostrador (ex.: '16', com o '1' no meio da célula)."""
        cfg = C.carregar()["vento_7seg"]
        for arq in sorted(FIXTURES.glob("mostrador_vento*.png")):
            esperado = int(re.fullmatch(r"mostrador_vento(\d+)", arq.stem).group(1))
            tela = np.zeros((600, 800, 3), np.uint8)
            tela[515:600, 180:340] = np.asarray(Image.open(arq).convert("RGB"))
            self.assertEqual(ler_sete_segmentos(tela, cfg), esperado, arq.name)


if __name__ == "__main__":
    unittest.main()

"""Medição da rolagem da câmera (mira/camera.py) com um recorte real do mapa."""
import sys
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from mira.camera import Camera  # noqa: E402

MAPA = np.asarray(Image.open(RAIZ / "tests" / "fixtures" / "mapa.png").convert("RGB"))


def quadro(dx, dy):
    """Janela 400x300 do mapa com o conteúdo deslocado (dx, dy) na tela."""
    y0, x0 = 75 - dy, 100 - dx
    return np.ascontiguousarray(MAPA[y0:y0 + 300, x0:x0 + 400])


class TestCamera(unittest.TestCase):
    def test_mede_deslocamentos(self):
        for dx, dy in ((0, 0), (12, 0), (-30, 8), (40, -25), (-3, -2)):
            cam = Camera([0, 0, 400, 300])
            cam.medir(quadro(0, 0))
            self.assertEqual(cam.medir(quadro(dx, dy)), (dx, dy), (dx, dy))

    def test_soma_varios_quadros(self):
        cam = Camera([0, 0, 400, 300])
        cam.medir(quadro(0, 0))
        total = np.zeros(2, int)
        for p in range(1, 9):                      # câmera andando 7 px por quadro
            total += cam.medir(quadro(7 * p, 0))
        self.assertEqual(tuple(total), (56, 0))

    def test_imagem_sem_relacao_nao_move(self):
        cam = Camera([0, 0, 400, 300])
        cam.medir(quadro(0, 0))
        ruido = np.random.default_rng(1).integers(0, 255, (300, 400, 3), dtype=np.uint8)
        self.assertEqual(cam.medir(ruido), (0, 0))


if __name__ == "__main__":
    unittest.main()

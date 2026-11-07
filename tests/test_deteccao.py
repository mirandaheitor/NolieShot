import math
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mira.deteccao import (LeitorDigitos, binarizar, ler_angulo_seta, nome_arquivo_char,  # noqa: E402
                           segmentar)


def render(texto: str, escala=2) -> np.ndarray:
    # HUD típico: fonte de largura fixa com espaço entre os caracteres
    fonte = ImageFont.load_default()
    img = Image.new("RGB", (6 + 10 * len(texto), 16), (10, 10, 30))
    d = ImageDraw.Draw(img)
    for i, c in enumerate(texto):
        d.text((3 + 10 * i, 1), c, fill=(240, 240, 240), font=fonte)
    return np.asarray(img.resize((img.width * escala, img.height * escala), Image.NEAREST))


class TestDigitos(unittest.TestCase):
    def test_aprende_e_le(self):
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            # "ensina" como o calibrador faz: um exemplo por caractere
            for amostra in ("0123456789", "-5"):
                rgb = render(amostra)
                mask = binarizar(rgb, 128)
                caixas = segmentar(mask)
                self.assertEqual(len(caixas), len(amostra))
                for i, (c, (x0, x1, y0, y1)) in enumerate(zip(amostra, caixas)):
                    Image.fromarray((mask[y0:y1, x0:x1] * 255).astype(np.uint8)).save(
                        pasta / f"{nome_arquivo_char(c)}_{amostra}_{i}.png")
            leitor = LeitorDigitos(pasta)
            for v in (0, 7, 45, 90, 38, -12, -90):
                self.assertEqual(leitor.ler_int(render(str(v)), 128), v)

    def test_sem_templates(self):
        self.assertIsNone(LeitorDigitos(Path("nao_existe")).ler_int(render("12"), 128))


class TestSeta(unittest.TestCase):
    def seta(self, ang, tam=41):
        img = Image.new("RGB", (tam, tam), (0, 0, 40))
        d = ImageDraw.Draw(img)
        c = (tam - 1) / 2
        r = tam * 0.42
        ux, uy = math.cos(math.radians(ang)), -math.sin(math.radians(ang))
        ponta = (c + ux * r, c + uy * r)
        cauda = (c - ux * r, c - uy * r)
        d.line([cauda, ponta], fill=(255, 230, 40), width=2)
        px, py = -uy, ux
        base = (c + ux * r * 0.45, c + uy * r * 0.45)
        d.polygon([ponta, (base[0] + px * 6, base[1] + py * 6), (base[0] - px * 6, base[1] - py * 6)],
                  fill=(255, 230, 40))
        return np.asarray(img)

    def test_angulos(self):
        for ang in range(0, 360, 15):
            lido = ler_angulo_seta(self.seta(ang), [180, 180, 0], [255, 255, 140])
            erro = abs((lido - ang + 180) % 360 - 180)
            self.assertLessEqual(erro, 8, f"esperado {ang}, lido {lido:.1f}")


class TestAjuste(unittest.TestCase):
    def test_recupera_constantes(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ferramentas"))
        from ajustar_constantes import erros  # noqa: E402
        from mira.fisica import Vento, angulo_absoluto, simular
        from mira.mobiles import MOBILES

        real = MOBILES[0].com(gravidade=4.1, efeito=0.052)
        amostras = []
        for ang, f, vf, va, dir_ in [(45, 220, 15, 0, True), (60, 300, 20, 120, False), (35, 180, 10, 250, True)]:
            origem = (300.0, 400.0) if dir_ else (1300.0, 400.0)
            pts = simular(angulo_absoluto(ang, dir_), f, origem, Vento(vf, va), real, dir_)
            impacto = next(p for p in pts if p[1] > 450)
            amostras.append(dict(angulo_hud=ang, direita=dir_, forca_usada=f, vento_forca=vf,
                                 vento_angulo=va, origem=origem, impacto=impacto))
        gs = np.linspace(3.5, 4.7, 61)
        es = np.linspace(0.03, 0.07, 41)
        G, E = np.meshgrid(gs, es, indexing="ij")
        media, _ = erros(amostras, MOBILES[0], G, E)
        i, j = np.unravel_index(np.argmin(media), media.shape)
        self.assertAlmostEqual(gs[i], 4.1, delta=0.05)
        self.assertAlmostEqual(es[j], 0.052, delta=0.003)


if __name__ == "__main__":
    unittest.main()

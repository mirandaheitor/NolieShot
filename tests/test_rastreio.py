"""Rastreio do personagem pela etiqueta de nome (bandeira + nome embaixo do mobile)."""
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from mira.rastreio import RastreioNome  # noqa: E402

FIX = RAIZ / "tests" / "fixtures"


class TestRastreio(unittest.TestCase):
    def test_segue_nome_em_outra_tela(self):
        a = np.asarray(Image.open(FIX / "nome_a.png").convert("RGB"))
        b = np.asarray(Image.open(FIX / "nome_b.png").convert("RGB"))
        with tempfile.TemporaryDirectory() as d:
            r = RastreioNome(Path(d) / "meu_nome.png", bandeira=RAIZ / "templates" / "bandeira.png")
            self.assertTrue(r.capturar(a, 160, 89))        # mouse em cima do "NolieCps"
            self.assertEqual(r.pos, (114, 80))
            r.pos = None                                    # força a busca na tela toda
            self.assertEqual(r.localizar(b), (142, 101))
            # o modelo fica salvo e é recarregado
            self.assertTrue(RastreioNome(Path(d) / "meu_nome.png").ativo)

    def test_nome_azul_pega_bandeira_e_nome(self):
        """Nome azul sobre céu azul: pela cor só sobrava a bandeira (igual em todo BR)."""
        img = np.asarray(Image.open(FIX / "jogadores.png").convert("RGB"))
        with tempfile.TemporaryDirectory() as d:
            r = RastreioNome(Path(d) / "meu_nome.png", bandeira=RAIZ / "templates" / "bandeira.png")
            self.assertTrue(r.capturar(img, 115, 63))           # mouse no "BigJake"
            self.assertEqual(r.pos, (73, 57))
            self.assertEqual(r.modelo.shape[:2], (16, 90))      # bandeira + 64 px de nome

    def test_lista_de_turnos_excluida(self):
        a = np.asarray(Image.open(FIX / "nome_a.png").convert("RGB"))
        tela = np.zeros((600, 800, 3), np.uint8)
        tela[480:496, 17:107] = a[80:96, 114:204]               # a mesma etiqueta "na lista"
        with tempfile.TemporaryDirectory() as d:
            r = RastreioNome(Path(d) / "m.png", excluir=[[0, 400, 185, 518]],
                             bandeira=RAIZ / "templates" / "bandeira.png")
            self.assertTrue(r.capturar(a, 160, 89))
            r.pos = None
            self.assertIsNone(r.localizar(tela))                # só existe na lista: não vale

    def test_sem_nome_nao_acha(self):
        a = np.asarray(Image.open(FIX / "nome_a.png").convert("RGB"))
        with tempfile.TemporaryDirectory() as d:
            r = RastreioNome(Path(d) / "meu_nome.png", bandeira=RAIZ / "templates" / "bandeira.png")
            r.capturar(a, 160, 89)
            vazio = np.full_like(a, 200)
            r.pos = None
            self.assertIsNone(r.localizar(vazio))


if __name__ == "__main__":
    unittest.main()

"""Ajusta gravidade e efeito do vento de um mobile a partir de tiros observados.

As constantes do CMX foram medidas no cliente da época; o seu servidor pode ter
valores diferentes. Este script acha o par (gravidade, efeito) que melhor explica
os impactos reais.

Coleta:
  1. No jogo, marque a origem (F5), anote a força que você realmente usou e atire.
  2. Antes do tiro (ou logo após) aperte F10: salva capturas/<data>.png + .json.
  3. No .json preencha  "forca_usada": 250  e  "impacto": [x, y]  (pixel onde caiu,
     dá para medir na imagem do F10 ou de um print do impacto).
  4. Tiros COM vento (e de lados diferentes) são necessários para estimar o efeito.

Uso:
    python ferramentas/ajustar_constantes.py --mobile Armor [pasta=capturas]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mira.fisica import Limites, Vento, angulo_absoluto, parametros, varrer, vento_quantizado  # noqa: E402
from mira.mobiles import MOBILES, indice_por_nome  # noqa: E402


def carregar(pasta: Path, nome_mobile: str) -> list[dict]:
    amostras = []
    for arq in sorted(pasta.glob("*.json")):
        d = json.loads(arq.read_text(encoding="utf-8"))
        if d.get("mobile", "").lower() != nome_mobile.lower():
            continue
        if d.get("forca_usada") is None or not d.get("impacto") or not d.get("origem"):
            continue
        amostras.append(d)
    return amostras


def erros(amostras, mob, G, E):
    """Erro (px) de cada amostra para cada combinação da grade G x E."""
    total = np.zeros(G.shape)
    pior = np.zeros(G.shape)
    lim = Limites(-3000, 5000, -8000, 4000)
    for a in amostras:
        direita = a["direita"]
        ang = angulo_absoluto(a["angulo_hud"], direita)
        alfa, beta, _ = parametros(ang, 0.0, mob.grub, direita)
        g = G + (0.004 * ang - 0.01 if mob.grub else 0.0)
        qx, qy = vento_quantizado(Vento(a["vento_forca"], a["vento_angulo"]))
        d, _, _ = varrer(alfa, beta, g, qx * E, qy * E, a["forca_usada"], a["origem"], a["impacto"], lim)
        total += d
        pior = np.maximum(pior, d)
    return total / len(amostras), pior


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mobile", required=True)
    ap.add_argument("pasta", nargs="?", default=str(Path(__file__).resolve().parents[1] / "capturas"))
    a = ap.parse_args()

    mob = MOBILES[indice_por_nome(a.mobile)]
    amostras = carregar(Path(a.pasta), mob.nome)
    if not amostras:
        sys.exit(f"Nenhuma amostra completa de {mob.nome} em {a.pasta} (precisa forca_usada + impacto + origem).")
    print(f"{len(amostras)} amostra(s) de {mob.nome}")

    atual, _ = erros(amostras, mob, np.array(mob.gravidade), np.array(mob.efeito))
    print(f"constantes atuais  g={mob.gravidade:.4f} ef={mob.efeito:.4f}  erro médio {float(atual):.1f}px")

    # grade grossa -> fina
    g_ini, g_fim, e_ini, e_fim = 1.0, 8.0, 0.0, 0.12
    for _ in range(3):
        gs = np.linspace(g_ini, g_fim, 71)
        es = np.linspace(e_ini, e_fim, 61)
        G, E = np.meshgrid(gs, es, indexing="ij")
        media, pior = erros(amostras, mob, G, E)
        i, j = np.unravel_index(np.argmin(media), media.shape)
        bg, be = gs[i], es[j]
        dg, de = (g_fim - g_ini) / 10, (e_fim - e_ini) / 10
        g_ini, g_fim = max(0.1, bg - dg), bg + dg
        e_ini, e_fim = max(0.0, be - de), be + de

    print(f"ajustado           g={bg:.4f} ef={be:.4f}  erro médio {media[i, j]:.1f}px  pior {pior[i, j]:.1f}px")
    sem_vento = all(s["vento_forca"] == 0 for s in amostras)
    if sem_vento:
        print("aviso: nenhuma amostra tem vento, então o 'ef' ajustado não significa nada.")
    print(f'\nPara usar: em mira/mobiles.py troque a linha do {mob.nome} por\n'
          f'    Mobile("{mob.nome}", {be:.4f}, {bg:.4f}{", grub=True" if mob.grub else ""}),')


if __name__ == "__main__":
    main()

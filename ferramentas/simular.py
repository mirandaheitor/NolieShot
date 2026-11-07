"""Gera uma imagem com trajetórias — útil para estudar o modelo sem abrir o jogo.

Exemplos:
    # melhor força para acertar o alvo + leque de forças de referência
    python ferramentas/simular.py --mobile Armor --angulo 50 --vento 12 --vento-ang 135 \
        --origem 150 420 --alvo 620 450 --leque --saida traj.png

    # sobre uma captura salva com F10 (usa origem/alvo/ângulo/vento do .json ao lado)
    python ferramentas/simular.py --amostra capturas/20261107_153000.png --saida traj.png
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mira.fisica import Limites, Vento, angulo_absoluto, simular  # noqa: E402
from mira.mobiles import MOBILES, indice_por_nome  # noqa: E402
from mira.solver import melhor_forca, melhores_angulos  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--amostra", help="PNG salvo com F10 (lê o .json de mesmo nome)")
    ap.add_argument("--mobile", default="Armor")
    ap.add_argument("--angulo", type=int, default=45, help="ângulo como aparece no HUD")
    ap.add_argument("--esquerda", action="store_true", help="mobile virado para a esquerda")
    ap.add_argument("--vento", type=int, default=0)
    ap.add_argument("--vento-ang", type=float, default=0, help="graus, 0=direita 90=cima")
    ap.add_argument("--origem", type=float, nargs=2, default=(150, 420))
    ap.add_argument("--alvo", type=float, nargs=2)
    ap.add_argument("--forca", type=int, help="força fixa (sem alvo)")
    ap.add_argument("--leque", action="store_true", help="desenha forças 50..400 de referência")
    ap.add_argument("--angulos", action="store_true", help="lista os melhores ângulos para o alvo")
    ap.add_argument("--tamanho", type=int, nargs=2, default=(800, 600))
    ap.add_argument("--saida", default="trajetoria.png")
    a = ap.parse_args()

    fundo = None
    if a.amostra:
        fundo = Image.open(a.amostra).convert("RGB")
        dados = json.loads(Path(a.amostra).with_suffix(".json").read_text(encoding="utf-8"))
        a.mobile, a.angulo, a.esquerda = dados["mobile"], dados["angulo_hud"], not dados["direita"]
        a.vento, a.vento_ang = dados["vento_forca"], dados["vento_angulo"]
        a.origem = dados["origem"] or a.origem
        a.alvo = dados["alvo"] or a.alvo
        if dados.get("forca_usada") is not None and a.forca is None:
            a.forca = dados["forca_usada"]

    mob = MOBILES[indice_por_nome(a.mobile)]
    direita = not a.esquerda
    vento = Vento(a.vento, a.vento_ang)
    ang_abs = angulo_absoluto(a.angulo, direita)
    w, h = fundo.size if fundo else a.tamanho
    lim = Limites(-1500, w + 1500, -5000, h + 200)

    img = fundo.copy() if fundo else Image.new("RGB", (w, h), (18, 20, 28))
    d = ImageDraw.Draw(img, "RGBA")
    try:
        d.font = ImageFont.truetype("consola.ttf", 13)  # fonte do Windows com acentos
    except OSError:
        pass
    if not fundo:
        for gx in range(0, w, 50):
            d.line([(gx, 0), (gx, h)], fill=(255, 255, 255, 18))
        for gy in range(0, h, 50):
            d.line([(0, gy), (w, gy)], fill=(255, 255, 255, 18))

    def curva(forca, cor, largura):
        pts = simular(ang_abs, forca, a.origem, vento, mob, direita, lim)
        d.line([tuple(p) for p in pts], fill=cor, width=largura, joint="curve")
        return pts

    if a.leque:
        for f in range(50, 401, 50):
            pts = curva(f, (255, 255, 255, 70), 1)
            vis = [p for p in pts if 0 <= p[0] < w and 0 <= p[1] < h]
            if vis:
                d.text(vis[-1], str(f), fill=(255, 255, 255, 140))

    linhas = [f"{mob.nome}  HUD {a.angulo}° ({'dir' if direita else 'esq'})  vento {a.vento}@{a.vento_ang:.0f}°"]
    if a.alvo:
        s = melhor_forca(a.angulo, a.origem, a.alvo, vento, mob, direita, limites=lim)
        curva(s.forca, (0, 229, 255, 255), 3)
        tx, ty = a.alvo
        d.ellipse([tx - 9, ty - 9, tx + 9, ty + 9], outline=(255, 59, 59), width=2)
        d.ellipse([s.ponto[0] - 3, s.ponto[1] - 3, s.ponto[0] + 3, s.ponto[1] + 3], fill=(255, 255, 255))
        linhas.append(f"melhor força {s.forca}  erro {s.erro:.1f}px")
        if a.angulos:
            for o in melhores_angulos(a.origem, a.alvo, vento, mob, direita, limites=lim):
                linhas.append(f"  alternativa: {o.angulo_hud}° f={o.forca} erro={o.erro:.1f}")
    if a.forca is not None:
        curva(a.forca, (255, 159, 26, 255), 2)
        linhas.append(f"força informada {a.forca} (laranja)")

    ox, oy = a.origem
    d.ellipse([ox - 5, oy - 5, ox + 5, oy + 5], fill=(57, 255, 20))
    for i, s in enumerate(linhas):
        d.text((10, 10 + 14 * i), s, fill=(255, 255, 255))

    img.save(a.saida)
    print("\n".join(linhas))
    print(f"imagem: {Path(a.saida).resolve()}")


if __name__ == "__main__":
    main()

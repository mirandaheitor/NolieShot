"""Calibrador do HUD: marca ROIs e ensina os dígitos.

Uso:
    python ferramentas/calibrar_hud.py                # captura da janela do jogo
    python ferramentas/calibrar_hud.py captura.png    # usa uma imagem salva (ex.: F10)

1. Escolha o tipo de região à direita e arraste um retângulo sobre a imagem.
   - angulo / vento_forca: só os números (sem ícones em volta).
   - vento_seta: quadrado CENTRADO no eixo de rotação da seta.
   - barra_forca: a barra inteira, do 0 ao máximo.
2. Ajuste o limiar até cada dígito aparecer separado (caixas vermelhas).
3. "Ensinar dígitos": digite o texto exibido (ex.: 47 ou -12). Repita com
   valores diferentes até cobrir 0-9 (e '-' se o HUD mostrar sinal).
4. "Salvar config".
"""
from __future__ import annotations

import sys
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog

import numpy as np
from PIL import Image, ImageDraw, ImageTk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mira import config as cfgmod  # noqa: E402
from mira.deteccao import (LeitorDigitos, binarizar, ler_angulo_seta, mascara_cor,  # noqa: E402
                           nome_arquivo_char, recortar, segmentar)
from mira.janela import Capturador, ativar_dpi, encontrar_janela, retangulo_cliente  # noqa: E402

TIPOS = ("angulo", "vento_forca", "vento_seta", "barra_forca")
CORES_TIPO = {"angulo": "#00ff66", "vento_forca": "#33aaff", "vento_seta": "#ffcc00", "barra_forca": "#ff55ff"}
ZOOM_PREVIEW = 6


class Calibrador:
    def __init__(self, root: tk.Tk, imagem: np.ndarray | None):
        self.root = root
        self.cfg = cfgmod.carregar()
        self.img: np.ndarray | None = None
        self.tipo = tk.StringVar(value="angulo")
        self.limiar = tk.IntVar(value=128)
        self._ini = None
        self._ret_temp = None

        root.title("Calibrador HUD — NolieShot")
        esq = tk.Frame(root)
        esq.pack(side="left", fill="both", expand=True)
        self.canvas = tk.Canvas(esq, bg="#202020", cursor="crosshair")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<ButtonPress-1>", self._press)
        self.canvas.bind("<B1-Motion>", self._move)
        self.canvas.bind("<ButtonRelease-1>", self._release)

        dir_ = tk.Frame(root, padx=8, pady=8)
        dir_.pack(side="right", fill="y")
        tk.Label(dir_, text="Região", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        for t in TIPOS:
            tk.Radiobutton(dir_, text=t, value=t, variable=self.tipo, fg=CORES_TIPO[t], selectcolor="#333",
                           command=self._trocar_tipo).pack(anchor="w")
        tk.Label(dir_, text="Limiar (dígitos)").pack(anchor="w", pady=(10, 0))
        tk.Scale(dir_, from_=0, to=255, orient="horizontal", variable=self.limiar, length=200,
                 command=lambda _: self._mudou_limiar()).pack(anchor="w")
        self.preview = tk.Label(dir_, bg="#000")
        self.preview.pack(anchor="w", pady=6)
        self.info = tk.Label(dir_, text="", justify="left", font=("Consolas", 9), wraplength=260)
        self.info.pack(anchor="w")
        for texto, cmd in [("Capturar do jogo", self._capturar), ("Abrir imagem...", self._abrir),
                           ("Ensinar dígitos", self._ensinar), ("Salvar config", self._salvar)]:
            tk.Button(dir_, text=texto, command=cmd, width=24).pack(anchor="w", pady=2)

        if imagem is not None:
            self._usar_imagem(imagem)
        else:
            self._capturar()

    # -- imagem -------------------------------------------------------------
    def _usar_imagem(self, img: np.ndarray):
        self.img = img
        self._foto = ImageTk.PhotoImage(Image.fromarray(img))
        self.canvas.config(width=img.shape[1], height=img.shape[0])
        self._redesenhar()

    def _capturar(self):
        hwnd = encontrar_janela(self.cfg["janela_titulo"], ignorar=("NolieShot", "MiraEstudo", "Calibrador"))
        ret = retangulo_cliente(hwnd) if hwnd else None
        if not ret:
            messagebox.showwarning("Calibrador", f"Janela {self.cfg['janela_titulo']!r} não encontrada.\n"
                                                 "Abra o jogo em modo janela ou use 'Abrir imagem'.")
            return
        self._usar_imagem(Capturador().capturar(ret))

    def _abrir(self):
        caminho = filedialog.askopenfilename(filetypes=[("Imagens", "*.png;*.bmp;*.jpg")],
                                             initialdir=cfgmod.PASTA_CAPTURAS)
        if caminho:
            self._usar_imagem(np.asarray(Image.open(caminho).convert("RGB")))

    # -- desenho ------------------------------------------------------------
    def _roi_de(self, tipo):
        if tipo == "barra_forca":
            b = self.cfg.get("barra_forca")
            if not b:
                return None
            w = round(self.cfg["forca_max"] * b["escala"])
            return [b["x0"], b["y"] - 6, w, 12]
        return self.cfg["rois"].get(tipo)

    def _redesenhar(self):
        c = self.canvas
        c.delete("all")
        if self.img is None:
            return
        c.create_image(0, 0, image=self._foto, anchor="nw")
        for t in TIPOS:
            r = self._roi_de(t)
            if r:
                x, y, w, h = r
                c.create_rectangle(x, y, x + w, y + h, outline=CORES_TIPO[t], width=1)
                c.create_text(x, y - 2, text=t, fill=CORES_TIPO[t], anchor="sw", font=("Consolas", 8))
        self._atualizar_preview()

    def _trocar_tipo(self):
        t = self.tipo.get()
        if t in self.cfg["limiar"]:
            self.limiar.set(self.cfg["limiar"][t])
        self._atualizar_preview()

    def _mudou_limiar(self):
        t = self.tipo.get()
        if t in ("angulo", "vento_forca"):
            self.cfg["limiar"][t] = self.limiar.get()
        self._atualizar_preview()

    def _atualizar_preview(self):
        t = self.tipo.get()
        crop = recortar(self.img, self._roi_de(t)) if self.img is not None else None
        if crop is None:
            self.preview.config(image="")
            self.info.config(text="Arraste um retângulo na imagem.")
            return
        if t in ("angulo", "vento_forca"):
            mask = binarizar(crop, self.limiar.get())
            caixas = segmentar(mask)
            im = Image.fromarray((mask * 255).astype(np.uint8)).convert("RGB")
            im = im.resize((im.width * ZOOM_PREVIEW, im.height * ZOOM_PREVIEW), Image.NEAREST)
            d = ImageDraw.Draw(im)
            for x0, x1, y0, y1 in caixas:
                d.rectangle([x0 * ZOOM_PREVIEW, y0 * ZOOM_PREVIEW, x1 * ZOOM_PREVIEW - 1, y1 * ZOOM_PREVIEW - 1],
                            outline=(255, 0, 0))
            leitor = LeitorDigitos(cfgmod.PASTA_TEMPLATES / t)
            lido, score = leitor.ler(crop, self.limiar.get())
            n = len(leitor.templates)
            self.info.config(text=f"{len(caixas)} caractere(s) separados\n"
                                  f"templates: {n}\nleitura: {lido!r} (score {score:.2f})")
        elif t == "vento_seta":
            sv = self.cfg["seta_vento"]
            mask = mascara_cor(crop, sv["rgb_min"], sv["rgb_max"])
            im = Image.fromarray((mask * 255).astype(np.uint8)).convert("RGB")
            im = im.resize((im.width * ZOOM_PREVIEW // 2, im.height * ZOOM_PREVIEW // 2), Image.NEAREST)
            a = ler_angulo_seta(crop, sv["rgb_min"], sv["rgb_max"])
            self.info.config(text=f"pixels da seta: {int(mask.sum())}\nângulo: {a if a is None else round(a)}\n"
                                  f"faixa RGB em config.json → seta_vento")
        else:
            im = Image.fromarray(crop)
            im = im.resize((min(im.width * 2, 400), im.height * 2), Image.NEAREST)
            b = self.cfg["barra_forca"]
            self.info.config(text=f"x0={b['x0']} y={b['y']} escala={b['escala']:.3f} px/força")
        self._prev = ImageTk.PhotoImage(im)
        self.preview.config(image=self._prev)

    # -- mouse --------------------------------------------------------------
    def _press(self, ev):
        self._ini = (ev.x, ev.y)

    def _move(self, ev):
        if not self._ini:
            return
        if self._ret_temp:
            self.canvas.delete(self._ret_temp)
        self._ret_temp = self.canvas.create_rectangle(*self._ini, ev.x, ev.y, outline="#ffffff", dash=(3, 2))

    def _release(self, ev):
        if not self._ini or self.img is None:
            return
        x0, y0 = self._ini
        x, y = min(x0, ev.x), min(y0, ev.y)
        w, h = abs(ev.x - x0), abs(ev.y - y0)
        self._ini = None
        if w < 3 or h < 3:
            return
        t = self.tipo.get()
        if t == "barra_forca":
            self.cfg["barra_forca"] = {"x0": x, "y": y + h // 2, "escala": w / self.cfg["forca_max"]}
        else:
            self.cfg["rois"][t] = [x, y, w, h]
        self._redesenhar()

    # -- ações --------------------------------------------------------------
    def _ensinar(self):
        t = self.tipo.get()
        if t not in ("angulo", "vento_forca"):
            messagebox.showinfo("Calibrador", "Selecione a região 'angulo' ou 'vento_forca'.")
            return
        crop = recortar(self.img, self._roi_de(t)) if self.img is not None else None
        if crop is None:
            return
        mask = binarizar(crop, self.limiar.get())
        caixas = segmentar(mask)
        texto = simpledialog.askstring("Ensinar dígitos", f"Digite exatamente o que aparece ({len(caixas)} caracteres):")
        if texto is None:
            return
        texto = texto.strip()
        if len(texto) != len(caixas):
            messagebox.showerror("Calibrador", f"Texto tem {len(texto)} caracteres mas foram separados {len(caixas)}.\n"
                                               "Ajuste o limiar ou a região.")
            return
        pasta = cfgmod.PASTA_TEMPLATES / t
        pasta.mkdir(parents=True, exist_ok=True)
        carimbo = time.strftime("%Y%m%d%H%M%S")
        for i, (c, (x0, x1, y0, y1)) in enumerate(zip(texto, caixas)):
            Image.fromarray((mask[y0:y1, x0:x1] * 255).astype(np.uint8)).save(
                pasta / f"{nome_arquivo_char(c)}_{carimbo}_{i}.png")
        self._atualizar_preview()

    def _salvar(self):
        cfgmod.salvar(self.cfg)
        messagebox.showinfo("Calibrador", f"Salvo em {cfgmod.ARQUIVO}")


def main():
    ativar_dpi()
    imagem = np.asarray(Image.open(sys.argv[1]).convert("RGB")) if len(sys.argv) > 1 else None
    root = tk.Tk()
    Calibrador(root, imagem)
    root.mainloop()


if __name__ == "__main__":
    main()

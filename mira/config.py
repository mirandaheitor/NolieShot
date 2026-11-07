"""Leitura/gravação do config.json com valores padrão."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

# Compilado (NolieShot.exe): config.json, templates/ e capturas/ ficam ao lado do exe,
# para continuarem editáveis. Rodando pelo Python: pasta do projeto.
RAIZ = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]
ARQUIVO = RAIZ / "config.json"
EXEMPLO = RAIZ / "config.example.json"   # versão publicada (sem IP/janela reais); base quando não há config.json
PASTA_TEMPLATES = RAIZ / "templates"
PASTA_CAPTURAS = RAIZ / "capturas"

PADRAO: dict = {
    "janela_titulo": "WindowName",
    "intervalo_ms": 60,
    "mobile": "Armor",
    "forca_max": 400,
    # true: o overlay não aparece em capturas (nem na nossa leitura do HUD, nem em OBS/prints).
    "ocultar_overlay_da_captura": True,
    # IPs (ou redes CIDR) de servidores SEUS fora da rede local, ex.: sua hospedagem.
    # Loopback e rede privada já são aceitos; qualquer outro servidor desativa o overlay.
    "servidores_permitidos": [],
    # Regiões do HUD em coordenadas da área cliente: [x, y, largura, altura].
    # Configure com ferramentas/calibrar_hud.py. Sem ROI o valor é manual (teclado numérico).
    "rois": {},
    # Limiar de luminância (0-255) para binarizar os dígitos de cada ROI.
    "limiar": {"angulo": 128, "vento_forca": 128},
    # Faixa RGB dos pixels da seta do vento.
    "seta_vento": {"rgb_min": [180, 180, 0], "rgb_max": [255, 255, 140]},
    # Barra de força: x da força 0, y do meio da barra, px por unidade de força.
    # Padrão = UI "nova" em 800x600 segundo o CMX (x=241, 1px por unidade).
    "barra_forca": {"x0": 241, "y": 575, "escala": 1.0},
    "cores": {
        "trajetoria": "#00e5ff",
        "origem": "#39ff14",
        "alvo": "#ff3b3b",
        "barra": "#ffe600",
        "texto": "#ffffff",
        "sugestao": "#ff9f1a",
        "atual": "#ff9f1a",
    },
}


def _mesclar(base: dict, extra: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _mesclar(out[k], v)
        else:
            out[k] = v
    return out


def carregar() -> dict:
    for arq in (ARQUIVO, EXEMPLO):
        if arq.exists():
            return _mesclar(PADRAO, json.loads(arq.read_text(encoding="utf-8")))
    return copy.deepcopy(PADRAO)


def salvar(cfg: dict) -> None:
    ARQUIVO.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")

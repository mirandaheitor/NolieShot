"""Atalhos globais por polling de GetAsyncKeyState (sem hooks de teclado)."""
from __future__ import annotations

import ctypes

_user32 = ctypes.windll.user32

VK = {
    "F5": 0x74, "F6": 0x75, "F7": 0x76, "F8": 0x77, "F9": 0x78,
    "F10": 0x79, "F11": 0x7A, "F12": 0x7B,
    "SHIFT": 0x10, "CTRL": 0x11,
    "NUM2": 0x62, "NUM4": 0x64, "NUM6": 0x66, "NUM8": 0x68,
    "NUM_MAIS": 0x6B, "NUM_MENOS": 0x6D, "NUM0": 0x60,
    "NUM1": 0x61, "NUM3": 0x63, "NUM5": 0x65, "NUM7": 0x67, "NUM9": 0x69,
    "NUM_VEZES": 0x6A, "NUM_DIVIDIR": 0x6F,
    "PAGE_UP": 0x21, "PAGE_DOWN": 0x22,
    "ESQUERDA": 0x25, "DIREITA": 0x27,
    "MOUSE_ESQ": 0x01,
    "INSERT": 0x2D, "DELETE": 0x2E,
}


def segurando(nome: str) -> bool:
    return bool(_user32.GetAsyncKeyState(VK[nome]) & 0x8000)


class Teclado:
    """Detecta a borda de descida (tecla acabou de ser apertada)."""

    def __init__(self):
        self._antes: dict[str, bool] = {}

    def apertou(self, nome: str) -> bool:
        agora = segurando(nome)
        antes = self._antes.get(nome, False)
        self._antes[nome] = agora
        return agora and not antes

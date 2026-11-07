"""Localiza a janela do jogo e captura a área cliente (só APIs públicas do Windows).

O CMX original lia pixels via syscall direta (NtGdiGetPixel) para escapar de
hooks de anti-cheat. Aqui usamos captura de tela comum (mss / BitBlt), que é o
suficiente para estudar detecção num servidor próprio.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes

import numpy as np

user32 = ctypes.windll.user32


def ativar_dpi() -> None:
    """Sem isso, em telas com escala != 100% as coordenadas da captura e do overlay não batem."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass


_WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def titulo(hwnd: int) -> str:
    n = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def encontrar_janela(trecho_titulo: str, ignorar: tuple[str, ...] = ("NolieShot", "MiraEstudo")) -> int | None:
    alvo = trecho_titulo.lower()
    achou: list[int] = []

    @_WNDENUMPROC
    def cb(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            t = titulo(hwnd)
            if alvo in t.lower() and not any(i in t for i in ignorar):
                achou.append(hwnd)
                return False
        return True

    user32.EnumWindows(cb, 0)
    return achou[0] if achou else None


def retangulo_cliente(hwnd: int) -> tuple[int, int, int, int] | None:
    """(x, y, largura, altura) da área cliente em coordenadas de tela."""
    if not user32.IsWindow(hwnd) or user32.IsIconic(hwnd):
        return None
    r = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(r))
    p = wintypes.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(p))
    w, h = r.right - r.left, r.bottom - r.top
    if w <= 0 or h <= 0:
        return None
    return p.x, p.y, w, h


def cursor_no_cliente(hwnd: int) -> tuple[int, int]:
    p = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(p))
    user32.ScreenToClient(hwnd, ctypes.byref(p))
    return p.x, p.y


def pid_da_janela(hwnd: int) -> int:
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def conexoes_remotas(pid: int) -> list[str]:
    """IPs remotos (IPv4) das conexões TCP estabelecidas do processo."""
    import socket
    import struct

    iphlpapi = ctypes.windll.iphlpapi
    tamanho = wintypes.DWORD(0)
    AF_INET, TCP_TABLE_OWNER_PID_ALL, ESTABLISHED = 2, 5, 5
    iphlpapi.GetExtendedTcpTable(None, ctypes.byref(tamanho), False, AF_INET, TCP_TABLE_OWNER_PID_ALL, 0)
    buf = ctypes.create_string_buffer(tamanho.value)
    if iphlpapi.GetExtendedTcpTable(buf, ctypes.byref(tamanho), False, AF_INET, TCP_TABLE_OWNER_PID_ALL, 0) != 0:
        return []
    n = struct.unpack_from("<I", buf, 0)[0]
    ips = []
    for i in range(n):
        estado, _, _, remoto, _, dono = struct.unpack_from("<6I", buf, 4 + i * 24)
        if dono == pid and estado == ESTABLISHED:
            ips.append(socket.inet_ntoa(struct.pack("<I", remoto)))
    return ips


def servidores_externos(hwnd: int, permitidos: list[str] = ()) -> list[str]:
    """Conexões do jogo que NÃO são loopback, rede local nem um servidor seu listado em
    `permitidos` (IPs ou redes, ex.: "203.0.113.10" ou "203.0.113.0/29").
    Lista vazia = servidor seu."""
    import ipaddress
    redes = []
    for p in permitidos:
        try:
            redes.append(ipaddress.ip_network(p.strip(), strict=False))
        except ValueError:
            pass   # vazio ou marcador do exemplo ("127.x.x"): não libera nada

    def proprio(ip: str) -> bool:
        a = ipaddress.ip_address(ip)
        return a.is_loopback or a.is_private or any(a in r for r in redes)

    return sorted({ip for ip in conexoes_remotas(pid_da_janela(hwnd)) if not proprio(ip)})


class Capturador:
    """Captura a área cliente como array RGB (altura, largura, 3)."""

    def __init__(self):
        import mss
        self._mss = mss.mss()

    def capturar(self, ret: tuple[int, int, int, int]) -> np.ndarray:
        x, y, w, h = ret
        shot = self._mss.grab({"left": x, "top": y, "width": w, "height": h})
        return np.asarray(shot)[:, :, 2::-1].copy()  # BGRA -> RGB

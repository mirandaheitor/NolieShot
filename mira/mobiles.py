"""Constantes físicas por mobile.

Origem: Plugins/Aimbot/subplugin/efeitos.cpp (tabela `effects[28]`) do CMX.
Cada entrada original era {efeito_vento, gravidade}, já em "unidades do integrador"
(ver mira/fisica.py). A ordem do índice é a mesma do `indiceMobile` do CMX.
"""
from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class Mobile:
    nome: str
    efeito: float      # multiplicador da aceleração do vento
    gravidade: float   # aceleração vertical (px / passo²·tick)
    grub: bool = False  # Grub tem correção própria de ângulo/gravidade no original
    obs: str = ""
    por_tras: bool = False  # atira para o lado oposto ao que está virado (CMX: Nak e Aduka)

    @property
    def suportado(self) -> bool:
        return self.gravidade > 0

    def com(self, **kw) -> "Mobile":
        return replace(self, **kw)


MOBILES: list[Mobile] = [
    Mobile("Armor", 0.0370, 3.6410),
    Mobile("Mage", 0.0386, 3.5090),
    Mobile("Nak", 0.0465, 4.5870, obs="tiro subterrâneo (T2/SS) não modelado", por_tras=True),
    Mobile("Trico", 0.0423, 4.1620),
    Mobile("BigFoot", 0.0456, 4.4920),
    Mobile("Boomer", 0.0640, 3.0360, obs="curva do bumerangue não modelada"),
    Mobile("Raon", 0.0403, 3.9800),
    Mobile("Lightning", 0.0355, 3.2150),
    Mobile("J.D", 0.0313, 3.0900),
    Mobile("A.Sate", 0.0387, 3.8000),
    Mobile("Ice", 0.0312, 3.0800),
    Mobile("Turtle", 0.0368, 3.6250),
    Mobile("Grub", 0.0303, 2.7400, grub=True),
    Mobile("Aduka", 0.0340, 3.2150, por_tras=True),
    Mobile("Kalsiddon", 0.0340, 3.3580),
    Mobile("JFrog", 0.0289, 2.6800),
    Mobile("Dragon", 0.0310, 2.8050),
    Mobile("Knight", 0.0330, 3.3500),
    Mobile("Phoenix", 0.0489, 4.8200, obs="espiral do T1 não modelada"),
    Mobile("Maya", 0.0489, 4.8200),
    Mobile("Wolf", 0.0489, 4.8200),
    Mobile("Tiburon", 0.0, 0.0, obs="sem constantes na base"),
    Mobile("BlueWhale", 0.0, 0.0, obs="sem constantes na base"),
    Mobile("Frank", 0.0489, 4.8200),
    Mobile("Princess", 0.0489, 4.8200),
    Mobile("Assassin", 0.0489, 4.8200),
    Mobile("ShadowWalker", 0.0289, 2.8550),
    Mobile("Carrior", 0.0384, 3.7750),
]

SUPORTADOS: list[int] = [i for i, m in enumerate(MOBILES) if m.suportado]


def indice_por_nome(nome: str) -> int:
    alvo = nome.strip().lower()
    for i, m in enumerate(MOBILES):
        if m.nome.lower() == alvo:
            return i
    raise KeyError(f"mobile desconhecido: {nome!r} (opções: {', '.join(m.nome for m in MOBILES)})")

"""NolieShot — overlay de trajetória para estudo (servidor offline).

Fluxo por quadro:
  1. acha a janela do jogo e captura a área cliente;
  2. lê ângulo / vento do HUD (se as ROIs estiverem calibradas; senão usa valores manuais);
  3. com origem (Num7) e alvo (Insert) marcados, calcula a melhor força;
  4. desenha trajetória, alvo e marcador na barra de força num overlay transparente
     que deixa os cliques passarem para o jogo.

Atalhos: veja COMANDOS abaixo (abre numa janela própria) ou o README.
"""
from __future__ import annotations

import ctypes
import json
import math
import threading
import time
import tkinter as tk
import traceback
from dataclasses import asdict, dataclass, field

from PIL import Image

from mira import config as cfgmod
from mira.barra import ler_barra
from mira.deteccao import LeitorDigitos, ler_sete_segmentos, recortar
from mira.mobile_det import detectar_agulha
from mira.tiros import NOMES_TIRO, T1, desenhar_tiro, ler_tipo_tiro
from mira.fisica import Limites, Vento, angulo_absoluto, simular
from mira.janela import (Capturador, ativar_dpi, cursor_no_cliente, encontrar_janela, retangulo_cliente,
                         servidores_externos)
from mira.mobiles import MOBILES, SUPORTADOS, indice_por_nome
from mira.solver import Solucao, melhor_forca, melhores_angulos
from mira.camera import Camera
from mira.jogadores import Jogadores, mais_perto
from mira.rastreio import RastreioNome
from mira.teclas import Teclado, segurando

COR_CHAVE = "#010101"  # pintado com esta cor = transparente

# Tudo no teclado numérico (NumLock ligado): o jogo usa F1-F6 e F8.
COMANDOS = [
    ("Num*", "sai do programa"),
    ("Num7", "trava a origem (com rastreio: corrige a origem em relação ao nome)"),
    ("Ctrl+Num7", "origem volta ao automático"),
    ("Num3", "mouse no seu nome: a origem passa a seguir seu personagem"),
    ("Ctrl+Num3", "desliga o rastreio pelo nome"),
    ("Insert", "define o alvo na posição do cursor"),
    ("Num9", "alvo = próximo rival na tela (e segue ele)"),
    ("Ctrl+Num9", "alvo para de seguir o rival"),
    ("Num1 / PgDn", "mobile seguinte"),
    ("Ctrl+Num1 / PgUp", "mobile anterior"),
    ("← / →", "lado para onde o mobile está virado (Nak/Aduka atiram para o outro)"),
    ("Num5", "mostra ou esconde o overlay"),
    ("Num0", "salva uma amostra"),
    ("Num/", "busca os ângulos"),
    ("Num+ / Num−", "ângulo +1 / −1 (com Ctrl, ±10)"),
    ("Num8 / Num2", "força do vento +1 / −1 (com Ctrl, ±10)"),
    ("Num4 / Num6", "gira o vento 5° (com Ctrl, 15°)"),
    ("Clique no compasso", "direção do vento = ponta da seta"),
    ("Ctrl + arrastar", "marca a largura de um tornado (até 5)"),
    ("Ctrl + clique no tornado", "remove aquele tornado"),
    ("Delete", "limpa todos os tornados"),
]


def janela_comandos(root: tk.Tk) -> tk.Toplevel:
    """Janela normal (fora do overlay) com a tabela de atalhos."""
    fundo, borda, cab = "#1e1e1e", "#3c3c3c", "#2d2d2d"
    jan = tk.Toplevel(root)
    jan.title("NolieShot — comandos")
    jan.configure(bg=borda)
    jan.resizable(False, False)
    fonte, fonte_cab = ("Segoe UI", 10), ("Segoe UI", 10, "bold")
    for col, titulo in enumerate(("Tecla", "Ação")):
        tk.Label(jan, text=titulo, font=fonte_cab, bg=cab, fg="#ffffff", anchor="center",
                 padx=10, pady=4).grid(row=0, column=col, sticky="nsew", padx=1, pady=1)
    for lin, (tecla, acao) in enumerate(COMANDOS, start=1):
        tk.Label(jan, text=tecla, font=fonte, bg=fundo, fg="#ffffff", anchor="w",
                 padx=10, pady=3).grid(row=lin, column=0, sticky="nsew", padx=1, pady=1)
        tk.Label(jan, text=acao, font=fonte, bg=fundo, fg="#ffffff", anchor="w",
                 padx=10, pady=3).grid(row=lin, column=1, sticky="nsew", padx=1, pady=1)
    return jan


@dataclass
class Estado:
    origem: tuple[int, int] | None = None
    alvo: tuple[int, int] | None = None
    mobile: int = 0
    direita: bool = True
    angulo_hud: int = 45
    vento_forca: int = 0
    vento_angulo: float = 0.0
    fonte_angulo: str = "manual"
    fonte_vento: str = "manual"
    fonte_origem: str = "manual"
    tiro: int = T1                      # 0=T1, 1=T2, 2=SS (LED verde do botão no HUD)
    fonte_tiro: str = "manual"
    forca_pino: int | None = None       # pino da barra (o que o jogador arrasta)
    forca_carga: int | None = None      # carga atual enquanto segura o espaço
    forca_anterior: int | None = None   # força do último tiro
    visivel: bool = True
    sugestoes: list = field(default_factory=list)


class Overlay:
    def __init__(self, root: tk.Tk, ocultar_da_captura: bool = True):
        self.root = root
        self.ocultar_da_captura = ocultar_da_captura
        root.title("NolieShot overlay")
        root.overrideredirect(True)
        root.configure(bg=COR_CHAVE)
        root.attributes("-topmost", True)
        root.attributes("-transparentcolor", COR_CHAVE)
        self.canvas = tk.Canvas(root, bg=COR_CHAVE, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self._geo = None
        root.update_idletasks()
        self._click_through()

    def _click_through(self):
        GWL_EXSTYLE = -20
        WS_EX_LAYERED, WS_EX_TRANSPARENT = 0x80000, 0x20
        WS_EX_TOOLWINDOW, WS_EX_NOACTIVATE = 0x80, 0x08000000
        u = ctypes.windll.user32
        hwnd = u.GetParent(self.root.winfo_id()) or self.root.winfo_id()
        estilo = u.GetWindowLongW(hwnd, GWL_EXSTYLE)
        u.SetWindowLongW(hwnd, GWL_EXSTYLE,
                         estilo | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE)
        # Some das capturas de tela (inclusive da nossa), para o desenho não contaminar
        # a leitura do HUD. WDA_EXCLUDEFROMCAPTURE exige Windows 10 2004+.
        # Desligue em config.json se quiser gravar o overlay com OBS/print.
        if self.ocultar_da_captura and not u.SetWindowDisplayAffinity(hwnd, 0x11):
            print("aviso: SetWindowDisplayAffinity falhou; evite ROIs embaixo do texto do overlay")

    def posicionar(self, ret):
        if ret is None:
            if self._geo is not None:
                self.root.withdraw()
                self._geo = None
            return
        if ret != self._geo:
            x, y, w, h = ret
            self.root.geometry(f"{w}x{h}+{x}+{y}")
            self.root.deiconify()
            self.root.attributes("-topmost", True)
            self._geo = ret

    # -- primitivas -------------------------------------------------------
    def texto(self, x, y, s, cor, anchor="nw"):
        c = self.canvas
        just = "right" if anchor.endswith("e") else "left"
        c.create_text(x + 1, y + 1, text=s, fill="#000000", anchor=anchor, justify=just, font=("Consolas", 10, "bold"))
        c.create_text(x, y, text=s, fill=cor, anchor=anchor, justify=just, font=("Consolas", 10, "bold"))

    def cruz(self, p, cor, r=8):
        x, y = p
        self.canvas.create_line(x - r, y, x + r, y, fill=cor, width=2)
        self.canvas.create_line(x, y - r, x, y + r, fill=cor, width=2)
        self.canvas.create_oval(x - r, y - r, x + r, y + r, outline=cor, width=1)


class App:
    def __init__(self):
        ativar_dpi()
        self.cfg = cfgmod.carregar()
        try:
            mob = indice_por_nome(self.cfg["mobile"])
        except KeyError:
            mob = 0
        self.estado = Estado(mobile=mob)
        self.teclado = Teclado()
        self.cap = Capturador()
        self.leitores = {k: LeitorDigitos(cfgmod.PASTA_TEMPLATES / k) for k in ("angulo", "vento_forca")}
        # a lista de turnos (canto inferior esquerdo) repete bandeira + nome de todos:
        # nem o rastreio do seu nome nem a busca de rivais podem achar nada ali
        lista = [self.cfg.get("lista_turnos", [0, 400, 185, 518])]
        rn = self.cfg.get("rastreio_nome", {})
        self.rastreio = RastreioNome(cfgmod.PASTA_TEMPLATES / "meu_nome.png",
                                     rn.get("limiar", 0.8), rn.get("margem", 80), excluir=lista,
                                     bandeira=cfgmod.PASTA_TEMPLATES / "bandeira.png")
        off = tuple(rn.get("offset", (25, -23)))   # origem − canto da etiqueta
        self.offset_nome = off if abs(off[0]) <= 80 and abs(off[1]) <= 80 else (25, -23)   # descarta valor absurdo
        self._agulha_t = 0.0                    # última vez que a agulha (seu turno) foi vista
        rv = self.cfg.get("rivais", {})
        self.jogadores = Jogadores(cfgmod.PASTA_TEMPLATES / "bandeira.png", rv.get("limiar", 0.85),
                                   rv.get("excluir", lista))
        self.offset_alvo = tuple(rv.get("offset_alvo", (38, -25)))   # bandeira -> corpo do mobile
        self.rival_pos: tuple[int, int] | None = None   # bandeira do rival seguido (Num9)
        self.rival_time: str | None = None
        self.tornados: list[list[int]] = []     # faixas [x_ini, x_fim] na tela (Ctrl + arrastar)
        self._arrasto: int | None = None        # x onde começou o Ctrl + arrastar
        cc = self.cfg.get("camera")
        self.camera = Camera(cc["area"], cc.get("resp_min", 0.4)) if cc else None
        self.hwnd = None
        self.ret = None
        self.ultima_img = None
        self._cache_chave = None
        self._cache_sol: Solucao | None = None
        self._cache_pts: list = []
        self._thread_angulos: threading.Thread | None = None
        self._ultima_busca_janela = 0.0
        self._ultima_checagem_rede = 0.0
        self._quadro = 0
        self._curva_congelada = None
        self._externos: list[str] = []

        self.root = tk.Tk()
        self.overlay = Overlay(self.root, bool(self.cfg["ocultar_overlay_da_captura"]))
        self.root.withdraw()
        self.comandos = janela_comandos(self.root)
        print(f"Procurando janela com título contendo {self.cfg['janela_titulo']!r}...")
        self.root.after(100, self.tick)

    # -- loop ------------------------------------------------------------
    def tick(self):
        try:
            if self._passo():
                self.root.after(int(self.cfg["intervalo_ms"]), self.tick)
            else:
                self.root.destroy()
        except Exception:
            traceback.print_exc()
            self.root.after(500, self.tick)

    def _passo(self) -> bool:
        agora = time.time()
        if (self.hwnd is None or not retangulo_cliente(self.hwnd)) and agora - self._ultima_busca_janela > 1.0:
            self._ultima_busca_janela = agora
            novo = encontrar_janela(self.cfg["janela_titulo"])
            if novo and novo != self.hwnd:
                print(f"Janela encontrada: hwnd={novo:#x}")
            self.hwnd = novo
        self.ret = retangulo_cliente(self.hwnd) if self.hwnd else None

        if self.teclado.apertou("NUM_VEZES"):
            return False
        if self.ret is not None and agora - self._ultima_checagem_rede > 2.0:
            # Projeto de estudo para servidor próprio: não roda com o jogo ligado a servidor externo.
            self._ultima_checagem_rede = agora
            externos = servidores_externos(self.hwnd, self.cfg.get("servidores_permitidos", []))
            if externos != self._externos:
                if externos:
                    print(f"Jogo conectado a servidor externo {', '.join(externos)}: overlay desativado. "
                          f"Se for o SEU servidor, adicione o IP em 'servidores_permitidos' no config.json.")
                elif self._externos:
                    print("Jogo em servidor próprio: overlay ativo.")
                self._externos = externos
        if self._externos:
            self.ret = None
        if self.ret is None:
            self.overlay.posicionar(None)
            return True

        self._ler_hud()
        self._atalhos()
        self.overlay.posicionar(self.ret if self.estado.visivel else None)
        if self.estado.visivel:
            self._desenhar()
        return True

    # -- leitura do HUD ----------------------------------------------------
    def _ler_hud(self):
        rois = self.cfg["rois"]
        seg7 = self.cfg.get("angulo_7seg")
        if not rois and not seg7:
            return
        img = self.cap.capturar(self.ret)
        self.ultima_img = img
        e = self.estado

        # câmera rolou: origem e alvo são pontos fixos no MAPA, andam junto com ele
        if self.camera is not None:
            dx, dy = self.camera.medir(img)
            if dx or dy:
                if e.origem is not None:
                    e.origem = (e.origem[0] + dx, e.origem[1] + dy)
                if e.alvo is not None:
                    e.alvo = (e.alvo[0] + dx, e.alvo[1] + dy)
                if self.rastreio.pos is not None:   # a busca do nome começa onde ele deve estar
                    self.rastreio.pos = (self.rastreio.pos[0] + dx, self.rastreio.pos[1] + dy)
                if self.rival_pos is not None:
                    self.rival_pos = (self.rival_pos[0] + dx, self.rival_pos[1] + dy)
                for tor in self.tornados:          # tornado só tem largura (x): a altura é a tela toda
                    tor[0] += dx
                    tor[1] += dx

        leitor = self.leitores["angulo"]
        crop = recortar(img, rois.get("angulo"))
        if seg7 or (crop is not None and leitor.pronto):
            v = ler_sete_segmentos(img, seg7) if seg7 else leitor.ler_int(crop, self.cfg["limiar"]["angulo"])
            if v is not None and -90 <= v <= 90:
                e.angulo_hud, e.fonte_angulo = v, "HUD"
            else:
                e.fonte_angulo = "HUD?"  # mantém o último valor bom

        leitor = self.leitores["vento_forca"]
        crop = recortar(img, rois.get("vento_forca"))
        vseg7 = self.cfg.get("vento_7seg")
        if vseg7 or (crop is not None and leitor.pronto):
            v = ler_sete_segmentos(img, vseg7) if vseg7 else leitor.ler_int(crop, self.cfg["limiar"]["vento_forca"])
            if v is not None and 0 <= v <= 40:
                e.vento_forca, e.fonte_vento = v, "HUD"
            else:
                e.fonte_vento = "HUD?"

        # direção do vento NÃO é lida do HUD: só pelo clique no compasso (ou Num4/Num6)

        tt =self.cfg.get("tipo_tiro")
        if tt:
            v = ler_tipo_tiro(img, tt)
            if v is not None:
                e.tiro, e.fonte_tiro = v, "HUD"

        b = self.cfg.get("barra_forca")
        if b and "pino_y" in b:
            leitura = ler_barra(img, b)
            estava_carregando = e.forca_carga is not None
            if leitura.pino is not None:
                e.forca_pino = leitura.pino
            e.forca_carga = leitura.carga
            if leitura.anterior is not None:
                e.forca_anterior = leitura.anterior
            if estava_carregando and leitura.carga is None and leitura.anterior is not None:
                self._registrar_tiro(leitura.anterior)

        # Origem, por prioridade (sem alternar entre fontes a cada quadro):
        #   1. Num7 (manual) trava;  2. agulha vista há < 0,5 s (= seu turno);  3. seu nome (Num3).
        etiqueta = self.rastreio.localizar(img) if self.rastreio.ativo else None
        agulha_recente = time.time() - self._agulha_t < 0.5
        if etiqueta is not None and e.fonte_origem != "manual" and not agulha_recente:
            e.origem = (etiqueta[0] + self.offset_nome[0], etiqueta[1] + self.offset_nome[1])
            e.fonte_origem = "nome"

        # a agulha só existe no seu turno e não muda durante a carga: procura a cada 3 quadros
        ag_cfg = self.cfg.get("agulha")
        self._quadro += 1
        if ag_cfg and e.fonte_origem != "manual" and e.forca_carga is None and self._quadro % 3 == 0:
            ag = detectar_agulha(img, e.angulo_hud, ag_cfg)
            if ag is not None:
                e.origem, e.fonte_origem = ag.origem, "agulha"   # o lado vem das setas
                self._agulha_t = time.time()
                if etiqueta is not None:   # a agulha é mais exata: recalibra o deslocamento do nome
                    self.offset_nome = (ag.origem[0] - etiqueta[0], ag.origem[1] - etiqueta[1])

        # alvo seguindo um rival (Num9): procura as etiquetas a cada 3 quadros; entre uma
        # busca e outra o alvo já anda com a câmera (acima)
        if self.rival_pos is not None and self.jogadores.pronto and self._quadro % 3 == 1:
            rivais = [r for r in self.jogadores.achar(img) if r.time == self.rival_time]
            r = mais_perto(rivais, self.rival_pos, raio=120)
            if r is not None:
                self.rival_pos = (r.x, r.y)
                e.alvo = (r.x + self.offset_alvo[0], r.y + self.offset_alvo[1])

    def _proximo_rival(self):
        """Num9: escolhe o próximo rival na tela (ordem da esquerda para a direita)."""
        e = self.estado
        if self.ultima_img is None or not self.jogadores.pronto:
            print("rivais: sem templates/bandeira.png ou sem captura da tela")
            return
        todas = self.jogadores.achar(self.ultima_img)
        eu = mais_perto(todas, (e.origem[0] - self.offset_nome[0], e.origem[1] - self.offset_nome[1])
                        if e.origem else None, raio=150)
        meu_time = eu.time if eu is not None and eu.time != "?" else self.cfg.get("rivais", {}).get("meu_time")
        if meu_time is None:
            print("rivais: não sei qual é o seu time (marque a origem/nome primeiro ou defina rivais.meu_time)")
            return
        rivais = sorted((r for r in todas if r.time not in (meu_time, "?") and r != eu), key=lambda r: r.x)
        if not rivais:
            print(f"rivais: nenhum rival na tela (seu time: {meu_time})")
            return
        atual = mais_perto(rivais, self.rival_pos, raio=40)
        i = rivais.index(atual) + 1 if atual in rivais else 0
        r = rivais[i % len(rivais)]
        self.rival_pos, self.rival_time = (r.x, r.y), r.time
        e.alvo = (r.x + self.offset_alvo[0], r.y + self.offset_alvo[1])
        print(f"alvo seguindo rival {i % len(rivais) + 1}/{len(rivais)} ({r.time}) em {e.alvo}")

    def _salvar_offset_nome(self, off):
        self.offset_nome = (int(off[0]), int(off[1]))
        self.cfg.setdefault("rastreio_nome", {})["offset"] = list(self.offset_nome)
        cfgmod.salvar(self.cfg)

    # -- teclado -----------------------------------------------------------
    def _atalhos(self):
        e, t = self.estado, self.teclado
        passo = 10 if segurando("CTRL") else 1
        if t.apertou("NUM7"):
            if segurando("CTRL"):
                e.fonte_origem = "auto?"   # destrava: a próxima agulha detectada assume
                print("origem: volta para detecção automática")
            elif self.rastreio.ativo and self.rastreio.pos is not None:
                # com o rastreio ligado, Num7 corrige onde fica a origem em relação ao nome
                e.origem, e.fonte_origem = cursor_no_cliente(self.hwnd), "nome"
                self._salvar_offset_nome((e.origem[0] - self.rastreio.pos[0], e.origem[1] - self.rastreio.pos[1]))
                print(f"origem = {e.origem}, a {self.offset_nome} do seu nome")
            else:
                e.origem, e.fonte_origem = cursor_no_cliente(self.hwnd), "manual"
                print(f"origem travada em {e.origem} (Ctrl+Num7 volta ao automático)")
        if t.apertou("NUM3"):
            if segurando("CTRL"):
                self.rastreio.desligar()
                e.fonte_origem = "auto?"
                print("rastreio pelo nome desligado")
            elif self.ultima_img is None:
                print("rastreio: ainda sem captura da tela, tente de novo")
            else:
                cur = cursor_no_cliente(self.hwnd)
                if self.rastreio.capturar(self.ultima_img, *cur):
                    px, py = self.rastreio.pos
                    if e.origem is not None:   # mantém a origem atual, agora presa ao nome
                        self._salvar_offset_nome((e.origem[0] - px, e.origem[1] - py))
                    print(f"rastreio: seguindo seu nome em {self.rastreio.pos} "
                          f"(origem a {self.offset_nome}; Num7 corrige, Ctrl+Num3 desliga)")
                else:
                    print("rastreio: não achei nome colorido embaixo do mouse")
        if t.apertou("NUM9"):
            if segurando("CTRL"):
                self.rival_pos = None
                print("alvo parou de seguir o rival (fica onde está)")
            else:
                self._proximo_rival()
        if t.apertou("INSERT"):
            self.rival_pos = None                 # alvo na mão: para de seguir rival
            e.alvo = cursor_no_cliente(self.hwnd)
            print(f"alvo = {e.alvo}")
        passo_mobile = 0
        if t.apertou("NUM1"):
            passo_mobile = -1 if segurando("CTRL") else 1
        if t.apertou("PAGE_DOWN"):
            passo_mobile = 1
        if t.apertou("PAGE_UP"):
            passo_mobile = -1
        if passo_mobile:
            i = SUPORTADOS.index(e.mobile) if e.mobile in SUPORTADOS else 0
            e.mobile = SUPORTADOS[(i + passo_mobile) % len(SUPORTADOS)]
            self.cfg["mobile"] = MOBILES[e.mobile].nome
            cfgmod.salvar(self.cfg)
            print(f"mobile = {MOBILES[e.mobile].nome}")
        # lado = última seta de movimento pressionada (← esquerda, → direita)
        if t.apertou("ESQUERDA"):
            e.direita = False
        if t.apertou("DIREITA"):
            e.direita = True
        if t.apertou("NUM5"):
            e.visivel = not e.visivel
        if t.apertou("NUM0"):
            self._salvar_amostra()
        if t.apertou("NUM_DIVIDIR"):
            self._buscar_angulos()
        if t.apertou("NUM_MAIS"):
            e.angulo_hud, e.fonte_angulo = min(90, e.angulo_hud + passo), "manual"
        if t.apertou("NUM_MENOS"):
            e.angulo_hud, e.fonte_angulo = max(-90, e.angulo_hud - passo), "manual"
        if t.apertou("NUM8"):
            e.vento_forca, e.fonte_vento = min(40, e.vento_forca + passo), "manual"
        if t.apertou("NUM2"):
            e.vento_forca, e.fonte_vento = max(0, e.vento_forca - passo), "manual"
        if t.apertou("NUM4"):
            e.vento_angulo = (e.vento_angulo + (15 if passo > 1 else 5)) % 360
        if t.apertou("NUM6"):
            e.vento_angulo = (e.vento_angulo - (15 if passo > 1 else 5)) % 360
        clique = t.apertou("MOUSE_ESQ")
        # Tornado (como no CMX): Ctrl + clique numa borda, arrasta até a outra e solta.
        # Ctrl + clique sem arrastar dentro de um tornado remove ele; Delete limpa todos.
        if clique and segurando("CTRL"):
            self._arrasto = cursor_no_cliente(self.hwnd)[0]
            clique = False
        elif self._arrasto is not None and not segurando("MOUSE_ESQ"):
            x1 = cursor_no_cliente(self.hwnd)[0]
            a, b = sorted((self._arrasto, x1))
            self._arrasto = None
            if b - a >= 6:
                self.tornados = (self.tornados + [[a, b]])[-5:]       # o CMX guardava até 5
                print(f"tornado marcado: x {a}..{b} (largura {b - a})")
            else:
                antes = len(self.tornados)
                self.tornados = [tor for tor in self.tornados if not tor[0] - 3 <= a <= tor[1] + 3]
                if len(self.tornados) < antes:
                    print("tornado removido")
        if t.apertou("DELETE") and self.tornados:
            self.tornados = []
            print("tornados limpos")
        comp = self.cfg.get("compasso_vento")
        if comp and clique and not segurando("CTRL") and e.visivel:
            cx, cy = comp["centro"]
            px, py = cursor_no_cliente(self.hwnd)
            if 3 <= math.hypot(px - cx, py - cy) <= comp["raio"] + 2:   # o clique também vai pro jogo: fora daqui não
                e.vento_angulo = round(math.degrees(math.atan2(-(py - cy), px - cx))) % 360
                print(f"direção do vento (compasso) = {e.vento_angulo}°")

    # -- cálculo -----------------------------------------------------------
    def _entradas(self):
        e = self.estado
        return (e.origem, e.alvo, e.mobile, self._direita_tiro(), e.angulo_hud, e.vento_forca, e.vento_angulo,
                tuple(map(tuple, self.tornados)))

    def _direita_tiro(self) -> bool:
        """Lado para onde o TIRO vai: o das setas (← / →), invertido para quem atira
        por trás (Nak e Aduka, como no PosicaoBot do CMX)."""
        e = self.estado
        return e.direita != MOBILES[e.mobile].por_tras

    def _limites(self):
        # origem/alvo podem estar fora da tela (câmera rolada): a caixa cobre os dois
        _, _, w, h = self.ret
        e = self.estado
        xs = [0, w] + [p[0] for p in (e.origem, e.alvo) if p is not None]
        ys = [h] + [p[1] for p in (e.origem, e.alvo) if p is not None]
        return Limites(x_min=min(xs) - 1500, x_max=max(xs) + 1500, y_min=-5000, y_max=max(ys) + 200,
                       tornados=tuple(map(tuple, self.tornados)))

    def _resolver(self):
        chave = self._entradas() + (self.ret[2], self.ret[3])
        if chave == self._cache_chave:
            return self._cache_sol, self._cache_pts
        e = self.estado
        mob = MOBILES[e.mobile]
        vento = Vento(e.vento_forca, e.vento_angulo)
        lim = self._limites()
        sol = melhor_forca(e.angulo_hud, e.origem, e.alvo, vento, mob, self._direita_tiro(),
                           int(self.cfg["forca_max"]), lim)
        pts = simular(angulo_absoluto(e.angulo_hud, self._direita_tiro()), sol.forca, e.origem, vento, mob, self._direita_tiro(), lim)
        self._cache_chave, self._cache_sol, self._cache_pts = chave, sol, pts
        return sol, pts

    def _buscar_angulos(self):
        e = self.estado
        if not (e.origem and e.alvo) or (self._thread_angulos and self._thread_angulos.is_alive()):
            return
        args = (e.origem, e.alvo, Vento(e.vento_forca, e.vento_angulo), MOBILES[e.mobile], self._direita_tiro())
        lim = self._limites()
        e.sugestoes = ["calculando..."]

        def trabalho():
            sols = melhores_angulos(*args, forca_max=int(self.cfg["forca_max"]), limites=lim)
            e.sugestoes = [f"{s.angulo_hud:>3}° f={s.forca:<3} erro={s.erro:.0f}px" for s in sols]

        self._thread_angulos = threading.Thread(target=trabalho, daemon=True)
        self._thread_angulos.start()

    # -- desenho -----------------------------------------------------------
    def _desenhar(self):
        ov, e, cores = self.overlay, self.estado, self.cfg["cores"]
        ov.canvas.delete("all")
        mob = MOBILES[e.mobile]
        ang_abs = angulo_absoluto(e.angulo_hud, self._direita_tiro())

        linhas = [
            f"NolieShot  {mob.nome} {'→' if self._direita_tiro() else '←'}"
            f"{' (atira por trás)' if mob.por_tras else ''}  {NOMES_TIRO[e.tiro]} [{e.fonte_tiro}]" +
            (f"  ({mob.obs})" if mob.obs else ""),
            f"Ângulo HUD {e.angulo_hud:>3}° [{e.fonte_angulo}]  disparo {ang_abs:.0f}°",
            f"Vento {e.vento_forca:>2} @ {e.vento_angulo:.0f}° [{e.fonte_vento}]",
            f"Origem {e.origem} [{e.fonte_origem}]",
        ]

        self._desenhar_compasso()
        self._desenhar_tornados()
        if e.origem:
            ov.cruz(e.origem, cores["origem"], 6)
        if e.alvo:
            ov.cruz(e.alvo, cores["alvo"], 10)

        # A curva segue o PINO (a escolha do jogador). Durante a carga ela fica congelada:
        # a carga só é mostrada como "quanto falta" para chegar no pino.
        if e.forca_carga is None and e.origem is not None:
            self._curva_congelada = None
        forca_atual = e.forca_pino
        if e.origem and forca_atual is not None:
            chave = (forca_atual, ang_abs, e.origem, e.vento_forca, e.vento_angulo, e.mobile, self._direita_tiro(), e.tiro)
            if e.forca_carga is not None and self._curva_congelada is not None:
                chave, des = self._curva_congelada
            else:
                vento = Vento(e.vento_forca, e.vento_angulo)
                des = desenhar_tiro(e.tiro, mob, e.angulo_hud, self._direita_tiro(), forca_atual, e.origem, vento,
                                    self._limites())
                if e.forca_carga is not None:
                    self._curva_congelada = (chave, des)
            self._desenhar_tiro(des, cores["atual"], tracejado=True)
            linha = f"Pino {chave[0]}"
            if e.forca_carga is not None:
                falta = chave[0] - e.forca_carga
                linha += f"   carga {e.forca_carga}  ({'SOLTE' if abs(falta) <= 2 else f'falta {falta:+d}'})"
            elif e.forca_anterior is not None:
                linha += f"   último tiro {e.forca_anterior}"
            linhas.append(linha)

        if e.origem and e.alvo:
            sol, _ = self._resolver()
            des = desenhar_tiro(e.tiro, mob, e.angulo_hud, self._direita_tiro(), sol.forca, e.origem,
                                Vento(e.vento_forca, e.vento_angulo), self._limites())
            self._desenhar_tiro(des, cores["trajetoria"])
            px, py = sol.ponto
            ov.canvas.create_oval(px - 4, py - 4, px + 4, py + 4, outline="#ffffff", width=2)
            linhas.append(f"FORÇA {sol.forca}  (erro {sol.erro:.0f}px)")
            self._marcador_barra(sol.forca)
        elif not e.origem:
            linhas.append("Origem: aparece sozinha no seu turno (ou mouse no canhão + Num7)")
        else:
            linhas.append("Mouse no alvo + Insert para calcular a força ideal")

        if e.sugestoes:
            linhas.append("Ângulos (Num/):")
            linhas += ["  " + s for s in e.sugestoes]

        for i, s in enumerate(linhas):
            cor = cores["barra"] if s.startswith("FORÇA") else (cores["sugestao"] if s.startswith("  ") else cores["texto"])
            ov.texto(self.ret[2] - 8, 8 + i * 16, s, cor, anchor="ne")   # canto superior direito

    def _desenhar_tornados(self):
        c = self.overlay.canvas
        chao = self.cfg.get("chao_y", 515)
        cor = self.cfg["cores"].get("tornado", "#c070ff")
        faixas = [tuple(tor) for tor in self.tornados]
        if self._arrasto is not None:                      # prévia enquanto arrasta
            faixas.append(tuple(sorted((self._arrasto, cursor_no_cliente(self.hwnd)[0]))))
        for i, (a, b) in enumerate(faixas):
            previa = self._arrasto is not None and i == len(faixas) - 1
            for x in (a, b):
                c.create_line(x, 0, x, chao, fill=cor, width=1, dash=(4, 4) if previa else ())
            self.overlay.texto(a + 3, 4, f"tornado {b - a}px", cor)

    def _desenhar_compasso(self):
        """Círculo em volta do mostrador do vento: clique na ponta da seta para definir a
        direção. A agulha mostra a direção usada no cálculo."""
        comp = self.cfg.get("compasso_vento")
        if not comp:
            return
        c, e = self.overlay.canvas, self.estado
        cx, cy = comp["centro"]
        r = comp["raio"]
        c.create_oval(cx - r, cy - r, cx + r, cy + r, outline="#ffffff", width=1)
        for a in range(0, 360, 45):                   # marcas a cada 45° (maiores nos eixos)
            t = math.radians(a)
            r0 = r - (5 if a % 90 == 0 else 3)
            c.create_line(cx + r0 * math.cos(t), cy - r0 * math.sin(t),
                          cx + r * math.cos(t), cy - r * math.sin(t), fill="#ffffff", width=1)
        t = math.radians(e.vento_angulo)
        cor = "#ffe600"
        x, y = cx + r * math.cos(t), cy - r * math.sin(t)
        c.create_line(cx, cy, x, y, fill=cor, width=2, arrow="last", arrowshape=(7, 8, 3))

    def _desenhar_tiro(self, des, cor: str, tracejado: bool = False):
        c = self.overlay.canvas
        dash = (6, 3) if tracejado else ()
        for i, pts in enumerate(([des.principal] if des.principal else []) + des.extras):
            amostra = pts[::2] + ([pts[-1]] if len(pts) % 2 == 0 else [])   # sempre inclui o último ponto
            plano = [v for p in amostra for v in p]
            if len(plano) >= 4:
                principal = i == 0 and bool(des.principal)
                c.create_line(*plano, fill=cor, width=2 if principal else 1, smooth=True, dash=dash)
        for x, y in des.marcas:
            c.create_oval(x - 4, y - 4, x + 4, y + 4, outline="#ffffff", width=2)

    def _marcador_barra(self, forca: int):
        b = self.cfg.get("barra_forca")
        if not b:
            return
        x = b["x0"] + forca * b["escala"]
        y = b["y"]
        cor = self.cfg["cores"]["barra"]
        c = self.overlay.canvas
        c.create_line(x, y - 12, x, y + 12, fill=cor, width=2)
        c.create_polygon(x - 5, y - 18, x + 5, y - 18, x, y - 12, fill=cor, outline=cor)

    # -- estudo ------------------------------------------------------------
    def _registrar_tiro(self, forca: int):
        """Chamado quando a carga termina: salva o tiro com a força realmente usada.
        Falta só preencher 'impacto' no JSON para usar em ajustar_constantes.py."""
        if self.estado.origem is None:
            return
        print(f"tiro detectado: força {forca}, ângulo {self.estado.angulo_hud}, "
              f"vento {self.estado.vento_forca}@{self.estado.vento_angulo:.0f}")
        self._salvar_amostra(forca_usada=forca, prefixo="tiro_")

    def _salvar_amostra(self, forca_usada: int | None = None, prefixo: str = ""):
        """Salva captura + estado. Preencha depois 'forca_usada' e 'impacto' no JSON para
        usar em ferramentas/ajustar_constantes.py."""
        cfgmod.PASTA_CAPTURAS.mkdir(exist_ok=True)
        nome = prefixo + time.strftime("%Y%m%d_%H%M%S")
        img = self.ultima_img if self.ultima_img is not None else self.cap.capturar(self.ret)
        Image.fromarray(img).save(cfgmod.PASTA_CAPTURAS / f"{nome}.png")
        e = self.estado
        dados = {k: v for k, v in asdict(e).items() if k not in ("visivel", "sugestoes")}
        dados["mobile"] = MOBILES[e.mobile].nome
        dados["forca_sugerida"] = self._cache_sol.forca if self._cache_sol and self._cache_chave and \
            self._cache_chave[:7] == self._entradas() else None
        dados["forca_usada"] = forca_usada
        dados["impacto"] = None
        (cfgmod.PASTA_CAPTURAS / f"{nome}.json").write_text(json.dumps(dados, indent=2, ensure_ascii=False),
                                                            encoding="utf-8")
        print(f"amostra salva: capturas/{nome}.png/.json")

    def rodar(self):
        self.root.mainloop()


if __name__ == "__main__":
    App().rodar()

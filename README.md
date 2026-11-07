# NolieShot

Projeto de estudo de **detecção por imagem, cálculo de ângulo/força e desenho de
trajetória parabólica** para GunBound, para uso no seu **servidor offline/privado**.
Foi construído a partir do CMX (`E:\CMX`), aproveitando só a parte de física e de
leitura do HUD.

> Não use em servidores públicos com outros jogadores (ex.: Gitz): viola os termos
> de uso e estraga o jogo dos outros. Este projeto não tem, e não terá, recursos para
> esconder a ferramenta de anti-cheat.

## O que veio do CMX e o que ficou de fora

| CMX original | MiraEstudo |
|---|---|
| `subplugin/calculador.cpp` — integrador da trajetória | `mira/fisica.py` (porte fiel, com testes) |
| `subplugin/efeitos.cpp` — gravidade/efeito do vento por mobile | `mira/mobiles.py` |
| `calcularMelhor` — busca de força de 20 em 20 e depois de 1 em 1 | `mira/solver.py` — testa as 401 forças de uma vez (numpy), sem cair em mínimo local; e também sugere ângulos |
| `PixelUnit.cpp` — XOR de 6 pixels fixos por dígito | `mira/deteccao.py` — templates de dígitos aprendidos + leitura da seta do vento |
| Hook em DirectDraw para desenhar | overlay externo transparente, sem clique (`main.py`) |
| Leitura de memória, injeção de DLL, driver, syscalls diretas, VMProtect, HWID | **removidos** |

## Instalação

```
pip install numpy pillow mss opencv-python
```
(Python 3.10+; tkinter já vem com o Python do Windows.)

Rode o jogo em **modo janela**: um overlay não aparece por cima de tela cheia exclusiva.

## Executável (NolieShot.exe)

```
pip install pyinstaller
python -m PyInstaller --noconfirm --clean --onefile --console --uac-admin --name NolieShot ^
    --distpath dist/NolieShot --workpath build/work --specpath build main.py
copy config.json dist\NolieShot\  &  xcopy /E /I templates dist\NolieShot\templates
```

O exe pede administrador ao abrir (como o `.bat`). `config.json`, `templates/` e
`capturas/` ficam **ao lado do exe** (`mira/config.py` usa a pasta do executável quando
compilado), então dá para mudar `servidores_permitidos` e o resto sem recompilar.

## Uso

```
python main.py
```

Se o jogo foi aberto como administrador (o `Jogar.bat` do cliente local exige),
inicie o overlay com **`Iniciar MiraEstudo.bat`**, que também pede administrador.
Sem isso o Windows não deixa o overlay ler o teclado enquanto o jogo está em foco,
e nenhum atalho funciona (a leitura de tela continua funcionando).

Tudo no teclado numérico (NumLock ligado), porque o jogo usa F1–F6 e F8.

| Tecla | Ação |
|---|---|
| Num7 | marca e **trava** a origem na posição do mouse (a detecção automática não sobrescreve) |
| Ctrl+Num7 | destrava: volta a origem para a detecção automática pela agulha |
| Num3 | com o mouse em cima do **seu nome** (bandeira + nome embaixo do mobile): a origem passa a seguir seu personagem |
| Ctrl+Num3 | desliga o rastreio pelo nome |
| Insert | marca o **alvo** na posição do mouse |
| Num9 | alvo = **próximo rival** na tela, e o alvo passa a seguir ele (`mira/jogadores.py`) |
| Ctrl+Num9 | alvo para de seguir o rival |
| PgDn / PgUp | próximo / anterior mobile (também Num1 / Ctrl+Num1) |
| ← / → | lado para onde o mobile está virado = última seta de movimento pressionada. Nak e Aduka atiram por trás: o tiro sai para o lado oposto (`por_tras` em `mira/mobiles.py`) |
| Num5 | mostra / oculta o overlay |
| Num0 | salva captura + estado em `capturas/` (dataset de estudo) |
| Num/ | sugere ângulos (menor força que acerta, separados por ≥5°) |
| Num* | sai |
| Num+ / Num− | ângulo ±1 (Ctrl: ±10) quando não vem do HUD |
| Num8 / Num2 | força do vento ±1 |
| Num4 / Num6 | direção do vento ±5° (Ctrl: ±15°) |
| Clique no compasso | direção do vento = do centro do mostrador até o ponto clicado (ponta da seta) |

**Origem, por prioridade:** Num7 (trava) > agulha vista há menos de 0,5 s (seu turno) >
seu nome (Num3). Assim a origem não alterna entre fontes a cada quadro.

**Rivais (Num9):** acha as bandeiras (`templates/bandeira.png`) no mapa e separa os times
pela cor do nome (azul/laranja). Seu time = a etiqueta mais perto da sua origem. O alvo
fica em `rivais.offset_alvo` (padrão 38, −25) a partir da bandeira (centro do mobile) e
segue o rival (busca a cada 3 quadros + câmera). A lista de turnos (`lista_turnos`,
padrão 0,400–185,518) é ignorada aqui e no rastreio do nome, porque repete as etiquetas.

**Rastreio pelo nome** (`mira/rastreio.py`): o Num3 acha a bandeira sob o mouse e guarda
bandeira + 64 px do nome (funciona com nome azul ou laranja) em
`templates/meu_nome.png` (vale nas próximas vezes) e a cada quadro procura essa imagem
na tela (cv2.matchTemplate, perto da última posição; tela toda quando perde). A origem
fica a um deslocamento fixo do nome (`config.json → rastreio_nome.offset`): no seu turno a
agulha detectada recalibra esse deslocamento sozinha, e com o rastreio ligado o Num7
corrige na mão. Se o nome some (tornado, efeito por cima), a origem fica na última posição.

O compasso (círculo branco com marcas a cada 45° sobre o mostrador do vento) fica em
`config.json → compasso_vento` (`centro`, `raio`). A agulha amarela mostra a direção
usada no cálculo; ela só muda com o clique (ou Num4/Num6), então clique de novo a cada
turno. Só cliques dentro do círculo contam; o clique também chega ao jogo.

Com a **barra padrão** (800×600: mostrador redondo à esquerda, ângulo no círculo
preto ao lado e barra de força à direita), o `config.json` lê sozinho a cada turno:

| O quê | Onde | Chave |
|---|---|---|
| ângulo (inclusive negativo) | círculo preto, 7 segmentos 6×10 | `angulo_7seg` |
| força do vento | centro do mostrador, 2 dígitos 7×15 na cor (200,184,152) | `vento_7seg` |
| T1 / T2 / SS | botão selecionado fica amarelo; SS = nenhum dos dois e o SS mudou de cor | `tipo_tiro` |
| marcador de força | barra: zero em x=388, 1 px por ponto | `barra_forca` |

A **direção do vento** não é lida do HUD (a seta 3D não dá leitura confiável): use o
clique no compasso. A calibração da barra antiga ficou em
`config_hud_antigo.json`.

O overlay mostra a trajetória com a força ideal, o ponto da curva mais próximo do
alvo, a força sugerida e um marcador amarelo na **barra de força** (onde soltar o espaço).

Se houver mais de uma janela com "GunBound" no título, ponha o título exato em
`janela_titulo` no `config.json`.

## Calibração do HUD (detecção)

Sem calibração, ângulo e vento são manuais (teclado numérico). Para ler do HUD:

```
python ferramentas/calibrar_hud.py              # captura do jogo aberto
python ferramentas/calibrar_hud.py capturas/X.png
```

1. Escolha a região e arraste o retângulo: `angulo`, `vento_forca`, `vento_seta`
   (quadrado centrado no eixo da seta) e `barra_forca` (a barra inteira, de 0 a 400).
2. Ajuste o limiar até cada dígito ficar numa caixa vermelha separada.
3. **Ensinar dígitos**: digite o valor mostrado. Repita com telas diferentes até
   cobrir 0–9 (e `-`). Os templates vão para `templates/<região>/`.
4. A cor da seta fica em `config.json → seta_vento` (`rgb_min`/`rgb_max`); o preview mostra a máscara.
5. **Salvar config**.

## Ferramentas de estudo

**Imagem de trajetória**, sem precisar do jogo:
```
python ferramentas/simular.py --mobile Armor --angulo 55 --vento 14 --vento-ang 150 \
    --origem 140 430 --alvo 600 470 --leque --angulos --saida traj.png
python ferramentas/simular.py --amostra capturas/20261107_153000.png --saida traj.png
```

**Ajuste das constantes** ao seu servidor: o servidor pode ter física diferente da
época do CMX. Salve tiros com F10, preencha `forca_usada` e `impacto: [x, y]` no
`.json` e rode:
```
python ferramentas/ajustar_constantes.py --mobile Armor
```
O script procura numa grade o par (gravidade, efeito do vento) que minimiza o erro
e mostra a linha pronta para colar em `mira/mobiles.py`. Use tiros com e sem vento,
dos dois lados.

**Testes**: `python -m unittest discover -s tests`

## O modelo físico

Coordenadas de tela (y para baixo), passo fixo `T = 0.05`, até 1001 passos:

```
x += v·cos(θ)·T + usx + ax·T²/2        usx += ax·T
y -= v·sin(θ)·T + usy + (ay − g)·T²/2  usy += (ay − g)·T
ax, ay = trunc(vento·cos φ), trunc(vento·sin φ) × efeito_do_mobile
```

As peculiaridades (velocidade acumulada somada sem `·T`, vento truncado para
inteiro, `cos θ ± 0.002` conforme o lado, correção do Grub) foram mantidas de
propósito: as constantes do CMX foram medidas com **este** integrador.

O ângulo do HUD vira ângulo de disparo assim: direita → `θ = hud`, esquerda → `θ = 180 − hud`.

## T1, T2 e SS

O tipo de tiro é lido do HUD (LED verde aceso em cima do botão 1, 2 ou SS) e o
desenho segue a lógica do CMX (`mira/tiros.py`, porte de `TShMatrix::fillXxx`):

| Mobile | T1 | T2 | SS |
|---|---|---|---|
| Armor | — | — | marca onde o SS ativa |
| Turtle | — | 7 marcas no caminho | marca onde o SS ativa |
| Mage | — | marcas periódicas | — |
| BigFoot | 4 projéteis | 6 projéteis | 4 projéteis |
| Grub | — | 4 projéteis | — |
| Frank | — | — | leque de 5 (0° a −40°) |
| Trico | — | repolhos girando em volta | — |
| Maya | — | — | marca o pico e desenha a volta do maxado até a mão |
| Phoenix | — | — | desacelera no passo 42, sobe e mergulha |
| Wolf | — | — | 5 marcas com linha até o chão; depois do passo 120 mergulha |
| Kalsiddon | marca (força) | marca (força) | marca (força) |

Esses desenhos de SS são só visuais: a força sugerida continua vindo da trajetória comum.
O Boomer não tem SS no CMX (o código estava comentado).

**SS automático (barra padrão):** o T1/T2 vêm do botão amarelo. O SS é marcado quando
nenhum dos dois está amarelo **e** o botão SS sai da cor normal (`tipo_tiro.ss` no
`config.json`). Sem isso (fora do turno, por exemplo), fica o tipo anterior.

Diferença do original: o desvio de ângulo dos projéteis extras é aplicado à
elevação (ângulo do HUD), não ao ângulo absoluto, para o leque espelhar
corretamente quando o mobile está virado à esquerda.

## Limitações / próximos passos

- **Câmera** (`mira/camera.py`, `config.json → camera`): a rolagem da tela é medida
  quadro a quadro (correlação de fase na área do mapa) e origem/alvo andam junto, como
  pontos fixos no mapa. Dá para rolar até o inimigo, marcar o alvo (Insert) e a
  trajetória continua saindo do seu mobile fora da tela. Pulos grandes de câmera
  (> 150 px num quadro, como o salto para o jogador da vez) não são acompanhados: a
  origem se corrige sozinha quando seu nome/agulha aparece; o alvo, marque de novo.
- **Tornado** (`fisica.passar_tornado`, porte de `calculaTornado`): **Ctrl + clique** numa
  borda do tornado, arraste até a outra e solte (até 5). Ctrl + clique sem arrastar dentro
  de um remove; **Delete** limpa todos. Quando a trajetória entra na faixa, dá 3 voltas de
  borda a borda seguindo a inclinação de entrada e sai pelo outro lado com a mesma
  velocidade. Vale para o desenho **e** para a força sugerida; os tornados andam com a
  câmera. O **espelho** do CMX não foi portado, e o Phoenix SS/Wolf SS ignoram o tornado.
- Ainda faltam do `calculador.cpp`/`mobiles.cpp`: Nak (subterrâneo), T1/T2 do Phoenix,
  T2 da Maya, Raon e o espelho.
- Inclinação do terreno e o offset do canhão por mobile (`GetAimFix` no original)
  não foram usados: você clica direto na ponta do canhão.
- Colisão com o terreno não é simulada: a força sugerida é a da curva que passa mais perto do alvo.

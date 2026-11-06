# claude-videos

Edição de vídeo conversando com o [Claude Code](https://claude.com/claude-code): você grava,
descreve o estilo que quer, e o Claude transcreve, propõe cortes, corrige a cor, aplica zooms
nos momentos importantes, cria gráficos animados, legenda, coloca trilha sonora com ducking e
renderiza. Você aprova cada etapa.

Tudo roda **localmente, em containers Podman**. O container de edição **não tem acesso à
rede**, então o seu vídeo nunca sai da máquina.

```
vídeo bruto ──► Whisper ──► cortes ──► cor + zoom ──► gráficos (HyperFrames) ──► legendas + trilha ──► MP4
                 (texto)    (você aprova)              (HTML/GSAP → MOV alpha)    (ducking, loudnorm)
```

## Comece com uma frase

Este repositório é um **ferramental para o Claude Code**. Você não precisa instalar nada à mão:
abra o Claude Code em qualquer pasta e diga:

> Baixe o repositório https://github.com/elias-mb3/claude-videos e configure para mim.

O Claude clona o repositório, lê o [`CLAUDE.md`](CLAUDE.md) e delega a instalação ao
subagente `configurador`, que constrói os containers, baixa fontes e o modelo do Whisper e
valida tudo com `bin/verificar`. Só o que exigir você (como `sudo` para instalar o Podman)
volta para você. Depois:

> Edite o vídeo ~/Vídeos/gravacao.mp4 para o TikTok.

### Como o trabalho é dividido

| Quem | Faz o quê |
|---|---|
| **Opus** (sessão principal) | Orquestra: conversa com você, lê a transcrição, decide cortes, cor, zooms, gráficos, músicas e legendas, e confere a qualidade |
| Subagente `configurador` (Sonnet) | Instala e repara o ambiente |
| Subagente `executor-render` (Sonnet) | Roda as etapas demoradas (transcrição, renders) e devolve só um resumo |

Assim, o modelo mais capaz fica com as decisões criativas e o trabalho repetitivo sai mais
barato, sem encher o contexto principal com logs. Detalhes em [docs/modelos-e-tokens.md](docs/modelos-e-tokens.md).

## Exemplos de uso (presets em `estilos/`)

| Preset | Formato | Para quê | Características |
|---|---|---|---|
| `tiktok-reels` | 1080×1920 | TikTok, YouTube Shorts | Cortes secos (pausas > 0,35 s), legenda gigante palavra a palavra, punch-ins fortes, cor vibrante, −14 LUFS |
| `instagram-reels` | 1080×1920 | Reels | Visual limpo, legendas em minúsculas, respeita as áreas cobertas pela interface do app |
| `youtube` | 1920×1080 | Vídeo longo no YouTube | Ritmo de conversa, legenda em frase na base, capítulos no canto e `capitulos.txt` pronto para a descrição |
| `romantico` | 1080×1920 | Vídeo pessoal (declaração, pedido, aniversário) | Ritmo calmo, serifas elegantes, paleta rosé e dourado, trilha instrumental suave |

### Referências com um modelo multimodal (recomendado)

O Claude Code não assiste vídeos. Se você tem assinatura de algum **modelo multimodal que processa
vídeo**, use-o para analisar vídeos de referência (trechos do YouTube, TikTok ou Reels cujo estilo
você quer copiar) e gerar um Markdown com ritmo, legendas, zooms, gráficos, cor e áudio, com
timestamps e um bloco de parâmetros. Salve em `referencias/<estilo>/notas.md`. O Claude lê esse
arquivo e converte em preset, o que melhora muito o resultado em relação a descrever o estilo
de memória. O prompt pronto está em [`referencias/_modelo-analise.md`](referencias/_modelo-analise.md).

Crie o seu copiando um preset. Os campos são autoexplicativos: resolução, cor, ritmo, zoom,
legendas, paleta, fontes, posição dos gráficos e áudio.

## Requisitos

- Linux com **Podman** (testado no Fedora 44, rootless). Funciona com Docker trocando `podman` por `docker` nos scripts de `bin/`.
- ~12 GB livres (imagens + modelo Whisper large-v3 de ~3 GB).
- CPU basta. GPU não é necessária.
- [Claude Code](https://claude.com/claude-code). Os scripts também funcionam sem ele, à mão.

## Instalação manual (opcional)

```bash
git clone https://github.com/elias-mb3/claude-videos && cd claude-videos
bin/setup       # constrói as imagens, baixa fontes livres (OFL), GSAP e o modelo do Whisper
bin/verificar   # confere tudo; termina com PRONTO
```

O `bin/setup` é o único passo que usa a internet, além do `bin/ytdl`.

Opcional: `cp docs/claude-settings.exemplo.json .claude/settings.json` para usar o modelo
recomendado (Opus na sessão principal) e liberar os comandos do pipeline sem pedir permissão a cada vez,
mantendo bloqueado o `hyperframes publish`.

## Uso com o Claude Code

```bash
bin/novo-projeto viagem-praia tiktok-reels
cp ~/Vídeos/gravacao.mp4 projetos/viagem-praia/bruto/video.mp4
claude
> edite o vídeo do projeto viagem-praia
```

O Claude segue a skill [`editar-video`](.claude/skills/editar-video/SKILL.md):

1. **Estilo:** pergunta o destino e o tom, e lê `referencias/` se houver.
2. **Transcrição** com Whisper large-v3. Ele aponta nomes próprios e palavras duvidosas.
3. **Cortes:** pausas são comprimidas automaticamente. Cortes de conteúdo (falsos começos,
   repetições) são propostos para você aprovar.
4. **Cor:** gera uma comparação neutro/natural/quente/vibrante para você escolher.
5. **Zooms** (lento para emoção, punch para ênfase), **gráficos** (capítulos, cards, listas
   que aparecem no tempo da fala, citações, abertura e encerramento) e **trilha** (faixa principal
   nos momentos fortes, faixas de apoio com crossfade).
6. **Preview em 540p**, ajustes e **render final**.

Tudo que define o vídeo fica em `projetos/<nome>/projeto.json` (veja o
[modelo comentado](projetos/_modelo/projeto.json)). Ele é o estado do projeto: dá para fechar
o Claude, voltar outro dia e continuar dele.

## Uso manual (sem Claude)

```bash
E="bin/editor python3 scripts/video.py viagem-praia"
$E info            # resolução, rotação, duração
$E transcrever     # build/transcricao.md
$E cortes          # build/cortes.md
$E cor             # build/cor.jpg
# edite projetos/viagem-praia/projeto.json (zoom, gráficos, música, correções de legenda)
$E tudo --preview  # saida/viagem-praia_preview.mp4
$E tudo            # saida/viagem-praia_1080x1920.mp4
```

Músicas: `bin/ytdl viagem-praia "URL"` baixa o áudio em WAV para `projetos/viagem-praia/musicas/`.

## Estrutura

```
bin/            setup, verificar, editor (container sem rede), ytdl (container de download), novo-projeto
containers/     Containerfiles das duas imagens
scripts/        video.py: o pipeline inteiro, em etapas
estilos/        presets (TikTok, Reels, YouTube, romântico)
referencias/    suas referências de estilo + prompt para análise com modelo multimodal
projetos/       um diretório por vídeo (ignorado pelo git, exceto _modelo)
docs/           modelos e tokens, exemplo de settings do Claude Code
CLAUDE.md       regras para o Claude Code neste repositório
.claude/skills/ skill editar-video (o fluxo passo a passo)
.claude/agents/ subagentes configurador e executor-render
```

## Segurança e privacidade

- **Dois containers separados:** o `ytdl` tem rede e só enxerga `projetos/<p>/musicas`. O `editor`
  roda com `--network=none` e só tem rede quando você usa `NET=1` explicitamente.
- Os containers rodam rootless com `--userns=keep-id`, então os arquivos gerados são seus, e não do root.
- O `.gitignore` impede versionar vídeos, áudios e projetos.
- O HyperFrames tem um comando `publish`, que envia o projeto para a nuvem. Ele nunca é usado,
  e o exemplo de settings o bloqueia.
- A telemetria do HyperFrames é desativada no setup. Sem rede, ela não teria como sair de qualquer forma.

## Música e direitos autorais

O `bin/ytdl` existe para uso **pessoal e privado**, como um vídeo para alguém da família que não
será publicado. Para vídeos públicos, use trilhas com licença adequada (YouTube Audio Library,
Pixabay Music, Free Music Archive, bibliotecas pagas) ou as músicas licenciadas do próprio
app (TikTok e Instagram). Respeite os termos de uso das plataformas de onde baixar.

## Como funciona por dentro

- **Transcrição:** faster-whisper large-v3 (int8, CPU) com tempo de cada palavra e VAD.
- **Cortes precisos por frame:** cada trecho mantido é renderizado separadamente (cor + zoom),
  com micro-fades de áudio de 12 ms para evitar estalos, e concatenado sem recompressão.
- **Zoom:** expressão por frame no `scale` do ffmpeg, com easing smoothstep. A cada corte, o
  enquadramento alterna entre 100% e ~106% para disfarçar jump cuts.
- **Gráficos:** HTML + CSS + GSAP renderizados pelo [HyperFrames](https://github.com/heygen-com/hyperframes)
  como ProRes 4444 com transparência, e sobrepostos no tempo certo (os tempos são convertidos do
  vídeo original para o vídeo cortado).
- **Legendas:** ASS gerado a partir das palavras, com destaque karaokê e quebra em pausas e cortes.
  Fica gravado no vídeo via libass.
- **Áudio:** voz com filtro passa-alta, redução de ruído, EQ de presença e compressor. Música
  com crossfades e ducking por sidechain. Ao final, loudnorm no alvo do preset.

## Créditos

- [ffmpeg](https://ffmpeg.org), [faster-whisper](https://github.com/SYSTRAN/faster-whisper),
  [HyperFrames](https://github.com/heygen-com/hyperframes), [GSAP](https://gsap.com), [yt-dlp](https://github.com/yt-dlp/yt-dlp).
- Fontes (SIL Open Font License), baixadas no setup: Playfair Display, Great Vibes, Montserrat, Anton, Noto Sans.

Licença: MIT (veja `LICENSE`).

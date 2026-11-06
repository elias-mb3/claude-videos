# Prompt para analisar vídeos de referência com um modelo multimodal

O Claude Code não assiste vídeos. Se você tem acesso a um modelo que processa vídeo (por exemplo,
modelos multimodais com entrada de vídeo ou link do YouTube), use-o para transformar vídeos de
referência em um Markdown objetivo. Salve o resultado em `referencias/<estilo>/notas.md`. O
Claude lê esse arquivo e converte em parâmetros de edição.

Cole o prompt abaixo junto com o vídeo, ou o link do YouTube/TikTok:

---

Analise este vídeo como referência de **estilo de edição** (não de conteúdo). Responda em
Markdown, de forma objetiva e com números sempre que possível, exatamente nestas seções:

## Formato
Proporção, duração, plataforma provável.

## Ritmo
Duração média dos planos (s), frequência de cortes por minuto, se há jump cuts, se pausas de
fala são removidas, como o vídeo abre (gancho nos primeiros 3 s?).

## Legendas
Posição (% da altura), fonte (serifa/sans/condensada), peso, caixa (MAIÚSCULAS?), palavras por
vez, destaque da palavra falada (cor em hex), contorno/sombra/caixa de fundo, animação.

## Zoom e movimento
Punch-ins (quando, intensidade aproximada %), zooms lentos, tremidas, transições usadas.

## Gráficos
Tipos (títulos, capítulos, cards, setas, emojis, stickers), posição, estilo, duração na tela,
animação de entrada e saída.

## Cor
Aparência (natural/quente/fria/vibrante/dessaturada/filme), contraste, vinheta, grão.

## Áudio
Música (gênero, andamento, instrumental?), volume em relação à voz, efeitos sonoros (whoosh,
pop, ding) e onde aparecem.

## Trechos marcantes
3 a 6 momentos com o timestamp (mm:ss) e o que acontece de edição neles.

## Resumo em parâmetros
Um bloco JSON com: `pausa_min`, `pausa_alvo`, `legenda_tamanho_px_1080`, `legenda_max_palavras`,
`maiusculas`, `cor_destaque`, `zoom_punch`, `zoom_lento`, `cor_preset`
(neutro/natural/quente/vibrante), `musica_volume_relativo`.

---

Dica: analise de 2 a 4 vídeos do mesmo estilo e peça ao modelo um resumo consolidado no final.
O Claude transforma o JSON de "Resumo em parâmetros" num preset de `estilos/`.

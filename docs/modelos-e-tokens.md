# Qual modelo usar e como economizar tokens

Editar vídeo com o Claude Code é barato **se** o modelo nunca "olhar" o vídeo diretamente.
Quem faz o trabalho pesado são o ffmpeg, o Whisper e o HyperFrames, dentro do container.
O Claude lê texto curto (transcrição compacta, resumos) e miniaturas pequenas.

## Modelo recomendado

| Fase | Modelo | Por quê |
|---|---|---|
| Definir estilo, roteiro de cortes, escolher momentos de zoom/gráficos | **Opus** (5.5 ou mais novo) | Decisões criativas e leitura da transcrição inteira; errar aqui custa renders. |
| Executar etapas, ajustar `projeto.json`, re-renderizar, corrigir legenda | **Sonnet** (5.5 ou mais novo) | Tarefas mecânicas; bem mais barato e rápido. |
| Perguntas rápidas ("quanto falta?", "qual o loudness?") | **Haiku** | Suficiente para ler um log ou rodar um comando. |

O jeito mais simples: `"model": "opusplan"` (veja `docs/claude-settings.exemplo.json`). O Opus
planeja no modo de planejamento (Shift+Tab) e o Sonnet executa. Para trocar na hora, use `/model`.

## Onde os tokens vão embora (e como evitar)

| Desperdício | Faça isso |
|---|---|
| Ler `transcricao.json` (palavra a palavra com tempos: enorme) | Ler `transcricao.md`, que tem 1 linha por segmento. Para o tempo de uma palavra, `grep`. |
| Abrir quadros em 1080p para "ver como ficou" | `video.py <p> amostra` ou `cor`: folhas de contato de 270px por quadro. |
| Acompanhar render lendo o log a cada minuto | Rodar em background e esperar a notificação de término. |
| Reescrever `projeto.json` inteiro a cada ajuste | Edit pontual no campo que mudou. |
| Re-renderizar tudo por causa de uma legenda | Legendas/música/gráficos mudam só a etapa `final` (~2x a duração do vídeo). Só apague `build/seg_*.mkv` se mudou cor, zoom ou cortes. |
| Conversa longa com vários vídeos | `/compact` entre etapas, ou `/clear` e retomar pelo `projeto.json` (ele é o estado do projeto). |
| Renders finais para testar | `--preview` (540p, preset rápido) até aprovar. |

## Custo típico (vídeo de ~7 min)

- Transcrição compacta: ~5–8 mil tokens para ler uma vez.
- Cada folha de contato: ~1–2 mil tokens.
- Planejamento + 2 rodadas de ajuste: tipicamente bem abaixo de 150 mil tokens no total.

## Tempo de máquina (CPU, sem GPU, 12 núcleos)

| Etapa | Tempo aproximado |
|---|---|
| Transcrição (large-v3, int8) | ~1,3x a duração do vídeo |
| Gráficos (HyperFrames) | 5–20 s por gráfico |
| Segmentos (cor + zoom) | ~2x a duração |
| Final (gráficos + legendas + áudio, preset slow) | ~2,3x a duração |

Notebook: ligue na tomada e use o perfil de energia "desempenho". Na bateria, em modo
economia, tudo fica cerca de 3x mais lento.

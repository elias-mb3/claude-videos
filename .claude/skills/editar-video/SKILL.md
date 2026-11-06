---
name: editar-video
description: Fluxo completo para editar um vídeo neste repositório — definir estilo, transcrever, propor cortes, cor, zooms, gráficos (HyperFrames), legendas, trilha e render. Use sempre que o usuário pedir para editar, montar, legendar ou finalizar um vídeo, ou criar um novo projeto de vídeo.
---

# Editar um vídeo

Comandos: `E="bin/editor python3 scripts/video.py <projeto>"`. Etapas longas em background.

## 0. Projeto e estilo
1. Pergunte o destino (TikTok/Shorts, Reels, YouTube, pessoal) e o tom. Escolha o preset em
   `estilos/` (ou crie um novo copiando o mais próximo). Veja `referencias/` se o usuário tiver
   deixado referências.
2. `bin/novo-projeto <nome> <estilo>`; vídeo vai em `projetos/<nome>/bruto/` (ajuste `fonte`).
3. `$E info` — confira duração, rotação e se o formato bate com o estilo.

## 1. Transcrição
`$E transcrever` (background, ~1,3x a duração do vídeo em CPU). Leia `build/transcricao.md`.
Liste ao usuário: nomes próprios suspeitos, trechos `?[...]` de baixa confiança. Para dúvidas,
`$E trecho INICIO FIM`. Corrija via `legendas.correcoes` / `substituir_segmento`.

## 2. Cortes (aprovação)
Proponha em `cortes.remover` (falsos começos, ligar/desligar câmera, repetições) e
`manter_pausas` (respiros dramáticos). `$E cortes` → mostre o resumo de `build/cortes.md`.

## 3. Cor (aprovação)
`$E cor` → olhe `build/cor.jpg` e recomende um preset (`ajustes_estilo.cor`).

## 4. Zooms, gráficos e trilha
- Momentos-chave da transcrição → `zoom` (`lento` para emoção, `punch` para ênfase/humor).
- `graficos`: `capitulo`, `card`, `lista` (itens aparecem no tempo da fala), `citacao`;
  `abertura`/`encerramento` opcionais. Tempos = vídeo ORIGINAL (o script converte).
- Música: `bin/ytdl <projeto> "ytsearch5:termo" --flat-playlist --print "%(id)s|%(duration_string)s|%(title)s"`
  para buscar; depois baixe. Faixa principal (`destaque: true`) nos momentos mais fortes;
  faixas de apoio instrumentais no resto. `"ate": "fim"` vai até o final.

## 5. Render
1. `$E tudo --preview` (background). Para conferir, monte uma folha de contato 270px com
   ffmpeg sobre `saida/*_preview.mp4` em ~6 tempos (legendas, gráficos, zoom, abertura/fim).
2. Mostre ao usuário, ajuste, e só então `$E tudo` (final). Confira loudness com `ebur128`.
3. YouTube: entregue também `saida/capitulos.txt` para a descrição.

Gráficos só re-renderizam o que mudou; segmentos existentes são reaproveitados — apague
`build/seg_*.mkv` se mudar cor, zoom ou cortes.

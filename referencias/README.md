# Referências

Guarde aqui o que define o *estilo* de um vídeo antes de editar. O Claude lê esta pasta na
etapa 0 da skill `editar-video` e traduz as referências para um preset em `estilos/`.

## Como organizar

```
referencias/
  <nome-do-estilo>/
    notas.md        # o que você gosta: ritmo, legenda, cores, tipo de música, exemplos (links)
    quadros/        # prints/quadros de vídeos de referência (PNG/JPG pequenos, <= 540px)
    paleta.txt      # opcional: cores em hex, uma por linha
```

## O que escrever em `notas.md`

- **Destino:** TikTok, Reels, Shorts, YouTube, vídeo pessoal.
- **Ritmo:** cortes secos e rápidos, ou respiros longos.
- **Legenda:** palavra a palavra (karaokê) ou frase, MAIÚSCULAS ou não, posição, cor de destaque.
- **Gráficos:** minimalista, editorial, divertido, com emojis ou sem.
- **Cor:** natural, quente/filme, vibrante, dessaturada.
- **Música:** gênero, instrumental ou com voz, volume em relação à fala.
- **Links de referência:** vídeos cujo estilo você quer seguir. É só a referência; o download
  de vídeos de terceiros não é necessário nem recomendado.

Quadros de referência de terceiros servem só para estudo local. Não os versione se não tiver
direito de redistribuí-los. Esta pasta, exceto este README, pode ir para o `.gitignore`, se preferir.

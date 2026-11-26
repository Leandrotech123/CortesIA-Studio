# CortesIA Studio

Edição local gratuita para transformar uma gravação própria ou autorizada em cortes verticais.
Use o painel em português para importar, revisar e preparar os arquivos de Instagram,
YouTube Shorts e TikTok. O processamento roda no seu computador.

## Começar no Windows

1. Extraia o ZIP em uma pasta do Windows. Use WSL Ubuntu como distribuição padrão.
2. No Ubuntu, instale Python 3 com suporte a venv, FFmpeg com libass e libx264 e curl.
3. Na pasta extraída, rode uma vez `bash instalar-studio.sh` no Ubuntu.
4. No Windows, abra **Abrir CortesIA Studio.cmd**. Se quiser, crie um atalho para ele na Área de Trabalho.

No Linux, execute `bash abrir-studio.sh` e acesse http://localhost:8765/.
O painel atende somente no próprio computador. A instalação baixa dependências e um modelo de transcrição.
O YouTube pode exigir um runtime JavaScript compatível com o yt-dlp. Veja as instruções
em https://github.com/yt-dlp/yt-dlp/wiki/EJS se o extrator solicitar esse componente.

## Preparar um corte

Envie um MP4 ou MKV, ou informe um link de vídeo do YouTube que você pode baixar e editar.
Se o serviço bloquear a importação, envie o arquivo original. Em IA e Tecnologia, a fila produz cortes de 35 a 58 segundos com a tela inteira e a marca configurada em assets/marcas/ia.json e tecnologia.json. Em Games, a fila produz
cortes de 1min30s a 2min com capas, legendas e textos. Após revisar, selecione as redes e aprove os
arquivos para download. Para usar sua marca, ajuste `assets/marcas/games.json` antes
da primeira execução. A publicação nas redes é manual. A aba Radar pesquisa metadados públicos sem baixar vídeos. Para processar uma fonte, escolha o resultado e confirme que pode baixar e editar. O roteiro PT-BR é um rascunho baseado na transcrição local; fontes em outro idioma exigem tradução e revisão humana.

## Componentes e licenças

O código desta edição está sob AGPL-3.0. Consulte LICENSE, LICENSE-ORIGINAL e os avisos OFL em assets/fonts. O instalador baixa as
dependências separadamente. Esta edição distribui o painel e o motor FFmpeg local.
O editor Remotion e as mídias do espaço de trabalho ficam fora do ZIP.
Revise os direitos de uso da fonte e os termos do YouTube antes de importar.

## Radar e episódios

Na aba Radar, escolha Games ou IA/Tecnologia, idioma da busca e tema. A busca lista
até 10 referências sem baixar vídeos. O idioma da busca não confirma o idioma
da fonte e a lista não comprova viralização. Só processe uma fonte que você pode
baixar e editar. A opção Série curta no envio Games produz episódios de 35–58 s;
sem ela, o padrão Games continua em 90–120 s. IA/Tecnologia usa 35–58 s.
Cada episódio traz manchete independente da fala, roteiro revisável,
MP4 com áudio, MP4 sem áudio e guia cronológico. Fontes em inglês não são
traduzidas automaticamente para português: revise e complete o roteiro antes
de gravar. Publicação nas redes continua manual.

"""Seleção e exportação em lote de gameplay local para Kortexx Games."""
import argparse
from bisect import bisect_left, bisect_right
from datetime import datetime
import json
import logging
from pathlib import Path
import re
import subprocess
import tempfile
from uuid import uuid4
from zoneinfo import ZoneInfo

from cortes import ROOT, SINAIS_GAMES, ffmpeg, gravar, legendas, tempo

MARCA = ROOT / 'assets/marcas'
FONTES = ROOT / 'assets/fonts'
logger = logging.getLogger(__name__)
MINIMO, MAXIMO = 90, 120


def gerar_assets(marca):
    from PIL import Image, ImageDraw, ImageFont

    avatar = MARCA / 'kortexx_avatar.png'
    if not avatar.exists():
        img = Image.new('RGB', (1080, 1080), marca['fundo'])
        d = ImageDraw.Draw(img)
        d.polygon([(187, 280), (292, 280), (292, 800), (187, 800)], fill=marca['texto'])
        d.polygon([(292, 522), (443, 280), (570, 280), (404, 522),
                   (574, 800), (441, 800)], fill=marca['primaria'])
        d.polygon([(533, 280), (659, 280), (910, 800), (784, 800)], fill=marca['texto'])
        d.polygon([(784, 280), (910, 280), (659, 800), (533, 800)], fill=marca['primaria'])
        img.save(avatar)
    marca_dagua = MARCA / 'kortexx_watermark.png'
    if not marca_dagua.exists():
        img = Image.new('RGBA', (280, 60))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle((0, 0, 279, 59), radius=15, fill=(11, 13, 18, 204),
                            outline=marca['primaria'], width=2)
        fonte = ImageFont.truetype(str(FONTES / marca['legenda_fonte']), 26)
        d.text((140, 30), marca['handle'], anchor='mm', font=fonte, fill=marca['texto'])
        img.save(marca_dagua)
    return marca_dagua


def medir(video, duracao, audio):
    import numpy as np

    sinais = np.zeros((int(duracao) + 2, 2))
    # Um quadro pequeno por segundo, com diferenças entre quadros consecutivos.
    dados = subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(video),
        '-an', '-vf', 'fps=1,scale=64:36,format=gray', '-pix_fmt', 'gray',
        '-threads', '1', '-f', 'rawvideo', '-'])
    quadros = np.frombuffer(dados, dtype=np.uint8).reshape(-1, 2304)
    if len(quadros) > 1:
        valores = np.abs(np.diff(quadros.astype(np.int16), axis=0)).mean(axis=1)
        n = min(len(valores), len(sinais) - 1)
        sinais[1:n+1, 0] = valores[:n]
    if audio:
        import wave
        with wave.open(str(audio), 'rb') as wav:
            taxa = wav.getframerate()
            for i in range(len(sinais)):
                pcm = np.frombuffer(wav.readframes(taxa), dtype='<i2').astype(np.float32)
                if not pcm.size:
                    break
                sinais[i, 1] = np.sqrt(np.mean(pcm * pcm))
    for i in range(2):
        limite = np.percentile(sinais[:, i], 90)
        if limite:
            sinais[:, i] = np.minimum(sinais[:, i] / limite, 3)
    return sinais


def tokens(texto):
    return set(re.findall(r'\w{3,}', texto.lower()))


def selecionar(frases, sinais, duracao, brief, quantidade, excluir=()):
    palavras = [w for frase in frases for w in frase]
    instantes = [w['inicio'] for w in palavras]
    inicios = [-.3] + [f[0]['inicio'] for f in frases]
    finais = [f[-1]['fim'] for f in frases] + [duracao + .4]
    termos = tokens(brief)
    candidatos = []
    # Cada janela é pontuada por fala e por sinais observáveis de imagem e som.
    for base in range(0, max(1, int(duracao - MINIMO) + 1), 5):
        a = min(float(base), duracao - MINIMO)
        pos = bisect_left(inicios, a + .3)
        if pos < len(inicios) and inicios[pos] - a <= 5:
            a = max(0, min(duracao - MINIMO, inicios[pos] - .3))
        pos = bisect_right(finais, min(a + MAXIMO - .4, duracao - .4))
        b = finais[pos - 1] + .4 if pos and finais[pos - 1] + .4 >= a + MINIMO else min(duracao, a + 105)
        trecho = palavras[bisect_left(instantes, a):bisect_left(instantes, b)]
        trecho = [w for w in trecho if w['fim'] <= b]
        encontrados = tokens(' '.join(w['texto'] for w in trecho))
        visual, energia = sinais[int(a):max(int(a)+1, int(b))].max(axis=0)
        pistas = sorted(encontrados & SINAIS_GAMES)
        temas = sorted(encontrados & termos)
        nota = visual * 2 + energia * 2 + len(pistas) * 1.5 + len(temas) + min(len(trecho), 60) / 20
        candidatos.append(dict(inicio=round(a, 3), fim=round(b, 3), palavras=trecho,
            pontuacao=round(float(nota), 2), sinais_games=pistas, temas_encontrados=temas,
            movimento=round(float(visual), 2), energia=round(float(energia), 2)))
    cortes = []
    for c in sorted(candidatos, key=lambda c: -c['pontuacao']):
        if all(c['fim'] <= x['inicio'] or c['inicio'] >= x['fim'] for x in (*excluir, *cortes)):
            cortes.append(c)
            if len(cortes) == quantidade:
                break
    return cortes


def posicao_ass(marca):
    def cor(chave):
        valor = marca[chave][1:]
        return '&H00' + valor[4:6] + valor[2:4] + valor[:2]

    return (
        f'Style: Default,Montserrat ExtraBold,52,{cor("texto")},{cor("texto")},'
        '&H00000000,&H55000000,0,0,0,0,100,100,0,0,1,4,2,2,92,162,520,1\n'
        'Style: Hook,Bebas Neue,66,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,'
        '0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1\n'
    )


def renderizar(video, pasta, marca, corte, numero, creditos, tem_audio, marca_dagua):
    import shutil

    nome = f'corte_{numero:02d}'
    inicio, fim = corte['inicio'], corte['fim']
    duracao = fim - inicio
    gancho = ' '.join(w['texto'] for w in corte['palavras'][:8]).strip()
    gancho = (gancho[:42].rsplit(' ', 1)[0] if len(gancho) > 42 else gancho) or 'Momento da partida'
    gancho = gancho.translate(str.maketrans({'{': '(', '}': ')', '\\': '/'}))
    palavras = [dict(texto=w['texto'].upper(), inicio=w['inicio']-inicio, fim=w['fim']-inicio)
                for w in corte['palavras']]
    legendas(pasta, palavras)
    ass = pasta / 'legendas.ass'
    conteudo = ass.read_text(encoding='utf-8')
    conteudo = re.sub(r'^Style: Default,.*\n', posicao_ass(marca), conteudo, flags=re.M)
    conteudo = conteudo.replace('&H93FF49&', '&H00E6FF&')
    conteudo += f'Dialogue: 1,0:00:00.00,0:00:03.50,Hook,,0,0,0,,{{\\pos(105,260)\\fscx80}}{gancho}\n'
    ass.write_text(conteudo, encoding='utf-8')
    # A janela central mantém parte considerável do HUD e o plano de fundo preenche a tela.
    shutil.copyfile(marca_dagua, pasta / 'marca.png')
    (pasta / 'fonts').symlink_to(FONTES, target_is_directory=True)
    fundo, secundaria, primaria = (marca[k].replace('#', '0x') for k in ('fundo', 'secundaria', 'primaria'))
    video_filtro = (
        '[0:v]fps=60,split[bg][fg];'
        '[bg]scale=270:480:force_original_aspect_ratio=increase,crop=270:480,'
        f'boxblur=10:2,scale=1080:1920,drawbox=color={fundo}@0.64:t=fill[blur];'
        "[fg]scale=1458:820:force_original_aspect_ratio=increase,crop=1080:820,"
        f'drawbox=x=0:y=0:w=iw:h=ih:t=2:color={primaria}[game];'
        '[blur][game]overlay=0:480[main];'
        '[main][1:v]overlay=650:375,'
        f"drawbox=x=85:y=246:w=830:h=105:color={fundo}:t=fill:enable='lt(t,3.5)',"
        f"drawbox=x=85:y=246:w=6:h=105:color={primaria}:t=fill:enable='lt(t,3.5)',"
        'ass=legendas.ass:fontsdir=fonts,'
        f"drawbox=x=70:y=1410:w=870:h=4:color={secundaria}:t=fill,"
        f"drawbox=x=70:y=1410:w=870:h=4:color={primaria}:t=fill[base];"
        f"color=c={secundaria}:s=870x4:r=60[barra];"
        f"[base][barra]overlay=x='70+870*min(t/{duracao},1)':y=1410,"
        'setsar=1,format=yuv420p[out]'
    )
    audio = [] if tem_audio else ['-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo']
    ffmpeg('-ss', inicio, '-i', video, '-i', 'marca.png', *audio, '-filter_complex', video_filtro,
           '-map', '[out]', '-map', '0:a:0' if tem_audio else '2:a:0', '-t', duracao,
           '-c:v', 'libx264', '-crf', '20', '-preset', 'fast', '-threads', '4',
           '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', nome + '.mp4', cwd=pasta)
    ffmpeg('-ss', 1, '-i', nome + '.mp4', '-frames:v', 1, '-update', 1, nome + '_capa.jpg', cwd=pasta)
    for arquivo in ('legendas.srt', 'legendas.ass', 'palavras.json'):
        (pasta / arquivo).rename(pasta / (nome + '_' + arquivo))
    (pasta / 'marca.png').unlink()
    (pasta / 'fonts').unlink()
    tag = '#' + re.sub(r'[^\w]', '', marca['nome'])
    textos = {
        'TikTok': f'{gancho}\n{tag} #Gameplay #Xbox #Jogos #Games',
        'YouTube Shorts': f'{gancho[:52] + " #Shorts"}\nUm momento da gameplay de {marca["nome"]}.',
        'Instagram Reels': f'{gancho}\nO que você faria nessa jogada? Comenta aí.\n{tag} #Gameplay #Xbox #ReelsGames',
    }
    (pasta / (nome + '_publicar.txt')).write_text(
        '\n\n'.join(f'{rede}\n{texto}' for rede, texto in textos.items()) + f'\n\nCréditos\n{creditos}\n',
        encoding='utf-8')
    gravar(pasta / (nome + '_meta.json'), dict(corte=corte, creditos=creditos, redes=textos))


def processar(video, brief, quantidade, progresso=print, origem=None, anterior=None, pronto=None):
    from faster_whisper import WhisperModel
    import shutil

    video = Path(video).resolve(strict=True)
    if not video.is_file() or not video.is_relative_to(ROOT / 'entrada'):
        raise ValueError('Use uma gravação própria dentro da pasta entrada/.')
    probe = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams',
        '-show_format', '-of', 'json', str(video)]))
    if not any(s['codec_type'] == 'video' for s in probe['streams']):
        raise ValueError('O arquivo não tem vídeo.')
    duracao = float(probe['format']['duration'])
    if duracao < MINIMO:
        raise ValueError('O modo Games precisa de pelo menos 1min30s de gravação.')
    tem_audio = any(s['codec_type'] == 'audio' for s in probe['streams'])
    marca = json.loads((MARCA / 'games.json').read_text(encoding='utf-8'))
    marca_dagua = gerar_assets(marca)
    dia = datetime.now(ZoneInfo('America/Fortaleza')).date().isoformat()
    destino = ROOT / 'publicacoes/games' / f'{dia}_{video.stem}'
    destino.parent.mkdir(parents=True, exist_ok=True)
    if destino.exists():
        destino = destino.with_name(f'{destino.name}-{uuid4().hex[:8]}')
    destino.mkdir()
    trabalho = ROOT / 'trabalho/games' / destino.name
    trabalho.mkdir(parents=True, exist_ok=True)
    (ROOT / 'tmp').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=ROOT / 'tmp', prefix='games-') as tmp:
        pasta = Path(tmp)
        audio = pasta / 'audio.wav' if tem_audio else None
        frases = []
        if audio:
            progresso('Extraindo áudio localmente.')
            ffmpeg('-i', video, '-map', '0:a:0', '-ac', 1, '-ar', 16000, audio)
            if anterior is not None:
                progresso('Reaproveitando a transcrição da gravação.')
                palavras = json.loads((anterior / 'palavras.json').read_text(encoding='utf-8'))
                for palavra in palavras:
                    if not frases or frases[-1][-1]['texto'].endswith(('.', '?', '!')) or (
                            palavra['inicio'] - frases[-1][-1]['fim'] > .5):
                        frases.append([])
                    frases[-1].append(palavra)
            else:
                progresso('Transcrevendo localmente.')
                modelo = WhisperModel(str(ROOT / 'cache/models/small'), device='cpu',
                                      compute_type='int8', cpu_threads=4, local_files_only=True)
                segmentos, _ = modelo.transcribe(str(audio), word_timestamps=True, vad_filter=True)
                for segmento in segmentos:
                    fala = [dict(inicio=w.start, fim=w.end, texto=w.word.strip())
                            for w in segmento.words or [] if w.end > w.start and w.word.strip()]
                    if fala:
                        frases.append(fala)
        progresso('Medindo movimento e energia para selecionar os melhores trechos.')
        excluir = ()
        if anterior is not None:
            plano_anterior = json.loads((anterior / 'plano.json').read_text(encoding='utf-8'))
            if plano_anterior['video'] != str(video.relative_to(ROOT)):
                raise ValueError('A transcrição anterior pertence a outro vídeo.')
            excluir = plano_anterior['cortes']
        cortes = selecionar(frases, medir(video, duracao, audio), duracao, brief, quantidade, excluir)
        creditos = f'Gravação própria via OBS Studio · {marca["handle"]}'
        if origem:
            creditos = f'Fonte autorizada para edição · {origem}'
        gravar(trabalho / 'plano.json', dict(video=str(video.relative_to(ROOT)), cortes=cortes))
        legendas(trabalho, [w for frase in frases for w in frase])
        arquivos, falhas = [], []
        for numero, corte in enumerate(cortes, 1):
            progresso(f'Renderizando corte {numero} de {len(cortes)}.')
            try:
                with tempfile.TemporaryDirectory(dir=pasta) as trecho:
                    renderizar(video, Path(trecho), marca, corte, numero, creditos, tem_audio, marca_dagua)
                    for arquivo in Path(trecho).iterdir():
                        shutil.move(str(arquivo), destino / arquivo.name)
                arquivos.append(str((destino / f'corte_{numero:02d}.mp4').relative_to(ROOT)))
                if pronto:
                    pronto(arquivos[-1])
            except (ValueError, OSError, subprocess.CalledProcessError):
                logger.exception('Falha em %s, corte %s', video.name, numero)
                falhas.append(numero)
        if not arquivos:
            raise ValueError('Nenhum corte renderizado. Confira logs/games.log.')
    return dict(arquivos=arquivos, falhas=falhas, cortes=cortes,
                destino=str(destino.relative_to(ROOT)),
                transcript=str((trabalho / 'palavras.json').relative_to(ROOT)),
                srt=str((trabalho / 'legendas.srt').relative_to(ROOT)))


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('video', type=Path)
    cli.add_argument('--brief', default='')
    cli.add_argument('--quantidade', type=int, choices=range(1, 11), default=3)
    args = cli.parse_args()
    (ROOT / 'logs').mkdir(exist_ok=True)
    logging.basicConfig(filename=ROOT / 'logs/games.log', level=logging.INFO)
    print(json.dumps(processar(args.video, args.brief, args.quantidade), ensure_ascii=False))

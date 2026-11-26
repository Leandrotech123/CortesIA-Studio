"""Cortes locais de IA e Tecnologia para revisão no painel."""
import json
import logging
from datetime import datetime
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from uuid import uuid4
from zoneinfo import ZoneInfo

from cortes import ROOT, ffmpeg, gravar, legendas

MARCAS = ROOT / 'assets/marcas'
FONTES = ROOT / 'assets/fonts'
MINIMO, MAXIMO = 35, 58
logger = logging.getLogger(__name__)


def gerar_assets(marca):
    from PIL import Image, ImageDraw, ImageFont

    MARCAS.mkdir(parents=True, exist_ok=True)
    prefixo = marca.get('asset_prefix', 'marca_tech')
    if not re.fullmatch(r'[a-z0-9_]+', prefixo):
        raise ValueError('Prefixo de asset inválido.')
    avatar = MARCAS / f'{prefixo}_avatar.png'
    if not avatar.exists():
        img = Image.new('RGB', (1080, 1080))
        pixels = img.load()
        for y in range(1080):
            for x in range(1080):
                t = (x + y) / 2158
                pixels[x, y] = (round(11 * (1-t) + 10*t),
                                round(13 * (1-t) + 31*t),
                                round(18 * (1-t) + 68*t))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle((165, 165, 915, 915), radius=100, outline=marca['destaque'], width=12)
        f = ImageFont.truetype(str(FONTES / marca['titulo_fonte']), 460)
        d.text((535, 540), marca.get('monograma', 'IA'), font=f, anchor='mm', fill=marca['texto'], stroke_width=2)
        d.line((185, 800, 410, 800, 535, 690, 685, 690, 885, 800),
               fill=marca['destaque'], width=12, joint='curve')
        for x, y in ((185,800), (410,800), (535,690), (685,690), (885,800)):
            d.ellipse((x-17,y-17,x+17,y+17), fill=marca['primaria'])
        img.save(avatar)
    watermark = MARCAS / f'{prefixo}_watermark.png'
    if not watermark.exists():
        img = Image.new('RGBA', (330, 68))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle((1,1,328,66), radius=16, fill=(10,31,68,217),
                            outline=marca['destaque'], width=2)
        f = ImageFont.truetype(str(FONTES / marca['legenda_fonte']), 27)
        d.text((165,34), marca['handle'], anchor='mm', font=f, fill=marca['texto'])
        img.save(watermark)
    return watermark


def frases_de_palavras(palavras):
    frases = []
    for w in palavras:
        if not frases or frases[-1][-1]['texto'].endswith(('.', '?', '!')) or w['inicio'] - frases[-1][-1]['fim'] > .65:
            frases.append([])
        frases[-1].append(w)
    return frases


def termos(texto):
    return set(re.findall(r'\w{3,}', texto.casefold()))


def selecionar(frases, brief, quantidade):
    palavras = [w for f in frases for w in f]
    if not palavras:
        raise ValueError('Nenhuma fala detectada. Confira o áudio da gravação.')
    candidatos = []
    brief_termos = termos(brief)
    for i, f in enumerate(frases):
        inicio = f[0]['inicio']
        bloco = []
        for prox in frases[i:]:
            if bloco and prox[0]['inicio'] - bloco[-1]['fim'] > 3.0:
                break
            if prox[-1]['fim'] - inicio > MAXIMO:
                break
            bloco.extend(prox)
            duracao = bloco[-1]['fim'] - inicio
            if duracao < MINIMO:
                continue
            encontrados = sorted(termos(' '.join(w['texto'] for w in bloco)) & brief_termos)
            gancho = len(termos(' '.join(w['texto'] for w in bloco[:12])) &
                         {'como','dica','erro','melhor','agora','novo','tutorial','compare'})
            nota = len(encontrados)*4 + gancho*2 + min(len(bloco), 100)/25 + (MAXIMO-duracao)/60
            candidatos.append(dict(inicio=round(max(0,inicio-.15),3),
                fim=round(bloco[-1]['fim']+.15,3), palavras=list(bloco),
                pontuacao=round(nota,2), temas_encontrados=encontrados))
    cortes = []
    for c in sorted(candidatos, key=lambda c: -c['pontuacao']):
        if all(c['fim'] <= x['inicio'] or c['inicio'] >= x['fim'] for x in cortes):
            cortes.append(c)
            if len(cortes) == quantidade:
                break
    return cortes


def ass_color(hex_color):
    h = hex_color.removeprefix('#')
    return '&H00' + h[4:6] + h[2:4] + h[:2]


def renderizar(video, pasta, marca, corte, numero, creditos, tem_audio, watermark, canal):
    nome = f'corte_{numero:02d}'
    inicio, fim = corte['inicio'], corte['fim']
    duracao = fim-inicio
    gancho = ' '.join(w['texto'] for w in corte['palavras'][:8]).strip()
    gancho = re.sub(r'[{}\\\r\n]', ' ', gancho).upper()
    gancho = (gancho[:40].rsplit(' ',1)[0] if len(gancho)>40 else gancho) or 'DICA DE TECNOLOGIA'
    palavras = [dict(texto=w['texto'], inicio=max(0,w['inicio']-inicio),
                     fim=min(duracao,w['fim']-inicio)) for w in corte['palavras']]
    legendas(pasta, palavras)
    ass = pasta / 'legendas.ass'
    conteudo = ass.read_text(encoding='utf-8')
    estilo = (f'Style: Default,Montserrat ExtraBold,58,{ass_color(marca["texto"])},'
              f'{ass_color(marca["texto"])},&H00000000,&H55000000,-1,0,0,0,100,100,0,0,1,4,1,2,'
              '120,140,565,1\n'
              f'Style: Hook,Bebas Neue,68,{ass_color(marca["texto"])},'
              f'{ass_color(marca["texto"])},&H00000000,&H00000000,0,0,0,0,'
              '100,100,0,0,1,0,0,7,98,0,0,1\n')
    conteudo = re.sub(r'^Style: Default,.*\n', estilo, conteudo, flags=re.M)
    conteudo = conteudo.replace('&H93FF49&', ass_color(marca['destaque']))
    primeira, _, resto = gancho.partition(' ')
    destaque_ass = ass_color(marca['destaque'])[4:]
    gancho_ass = r'{\c&H' + destaque_ass + '&}' + primeira + r'{\c&HFFFFFF&}' + (' ' + resto if resto else '')
    conteudo += f'Dialogue: 1,0:00:00.00,0:00:04.00,Hook,,0,0,0,,{{\\pos(98,270)}}{gancho_ass}\n'
    ass.write_text(conteudo, encoding='utf-8')
    from PIL import Image, ImageDraw
    overlay = Image.new('RGBA', (1080, 1920))
    ImageDraw.Draw(overlay).rounded_rectangle((18, 478, 1061, 1441),
        radius=18, outline=marca['destaque'], width=2)
    with Image.open(watermark) as selo:
        overlay.alpha_composite(selo.convert('RGBA'), (610, 385))
    overlay.save(pasta / 'marca.png')
    (pasta / 'fonts').symlink_to(FONTES, target_is_directory=True)
    fundo = marca['fundo'].replace('#','0x')
    secundaria = marca['secundaria'].replace('#','0x')
    primaria = marca['primaria'].replace('#','0x')
    destaque = marca['destaque'].replace('#','0x')
    # A tela 16:9 inteira cabe em 1040 px, sem perda de menus laterais.
    filtro = (
        f'color=c={fundo}:s=1080x1920:r=60[bg];'
        '[0:v]fps=60,scale=1040:960:force_original_aspect_ratio=decrease,'
        f'pad=1040:960:(ow-iw)/2:(oh-ih)/2:color={secundaria},setsar=1[screen];'
        '[bg][screen]overlay=20:480[layout];'
        f"[layout]drawbox=x=70:y=250:w=870:h=116:color={secundaria}@0.92:t=fill:enable='lt(t,4)',"
        f"drawbox=x=70:y=250:w=7:h=116:color={primaria}:t=fill:enable='lt(t,4)'[card];"
        '[card][1:v]overlay=0:0[brand];'
        '[brand]ass=legendas.ass:fontsdir=fonts,'
        f'drawbox=x=70:y=1410:w=870:h=4:color={primaria}:t=fill[base];'
        f'color=c={destaque}:s=870x4:r=60[bar];'
        f"[base][bar]overlay=x='70-870+870*min(t/{duracao},1)':y=1410,"
        'setsar=1,format=yuv420p[out]')
    audio = [] if tem_audio else ['-f','lavfi','-i','anullsrc=r=48000:cl=stereo']
    ffmpeg('-ss', inicio, '-i', video, '-i', 'marca.png', *audio,
           '-filter_complex', filtro, '-map','[out]',
           '-map','0:a:0' if tem_audio else '2:a:0', '-t',duracao,
           '-c:v','libx264','-crf','20','-preset','fast','-threads','4',
           '-c:a','aac','-b:a','192k','-movflags','+faststart',nome+'.mp4',cwd=pasta)
    ffmpeg('-ss', min(1,duracao/2),'-i',nome+'.mp4','-frames:v',1,'-update',1,
           nome+'_capa.jpg',cwd=pasta)
    for arquivo in ('legendas.srt','legendas.ass','palavras.json'):
        (pasta / arquivo).rename(pasta / (nome+'_'+arquivo))
    (pasta/'marca.png').unlink()
    (pasta/'fonts').unlink()
    curto = (gancho[:51].rsplit(' ',1)[0] if len(gancho)>51 else gancho)
    tag = '#IA' if canal=='ia' else '#Tecnologia'
    marca_tag = '#' + re.sub(r'[^\w]', '', marca['nome'])
    redes = {
        'TikTok': f'{gancho}\n{tag} {marca_tag} #DicaTech #Tutorial #Ferramentas',
        'YouTube Shorts': f'{curto[:51]} #Shorts\nVeja esta dica de {canal} em menos de um minuto.\n{tag} #Shorts',
        'Instagram Reels': f'{gancho}\nSalve para testar esta dica depois. Qual parte você quer ver em detalhe?\n{tag} {marca_tag} #TutorialTech'
    }
    (pasta/(nome+'_publicar.txt')).write_text(
        '\n\n'.join(f'{rede}\n{copy}' for rede,copy in redes.items())
        + f'\n\nCréditos\n{creditos}\n',encoding='utf-8')
    gravar(pasta/(nome+'_meta.json'),dict(corte=corte,creditos=creditos,redes=redes,
                                           marca=marca['nome'],canal=canal))


def processar(video, brief, quantidade, canal, progresso=print, origem=None, pronto=None):
    from faster_whisper import WhisperModel
    video = Path(video).resolve(strict=True)
    if canal not in ('ia','tecnologia') or not video.is_file() or not video.is_relative_to(ROOT/'entrada'):
        raise ValueError('Escolha IA ou Tecnologia e um vídeo da pasta entrada/.')
    probe = json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams',
                                                 '-show_format','-of','json',str(video)]))
    duracao = float(probe['format']['duration'])
    tem_audio = any(s['codec_type']=='audio' for s in probe['streams'])
    if duracao < MINIMO or not tem_audio:
        raise ValueError('O modo IA/Tecnologia precisa de ao menos 35 segundos com áudio.')
    marca = json.loads((MARCAS/(canal+'.json')).read_text(encoding='utf-8'))
    watermark = gerar_assets(marca)
    dia = datetime.now(ZoneInfo('America/Fortaleza')).date().isoformat()
    destino = ROOT/'publicacoes'/canal/f'{dia}_{video.stem}'
    destino.parent.mkdir(parents=True,exist_ok=True)
    if destino.exists():
        destino = destino.with_name(destino.name+'-'+uuid4().hex[:8])
    destino.mkdir()
    trabalho = ROOT/'trabalho'/canal/destino.name
    trabalho.mkdir(parents=True,exist_ok=True)
    try:
        progresso('Transcrevendo localmente com tempos por palavra.')
        modelo = WhisperModel(str(ROOT/'cache/models/small'),device='cpu',compute_type='int8',
                              cpu_threads=4,local_files_only=True)
        segmentos, _ = modelo.transcribe(str(video),word_timestamps=True,vad_filter=True)
        palavras = [dict(inicio=w.start,fim=w.end,texto=w.word.strip())
                    for s in segmentos for w in s.words or []
                    if w.end>w.start and w.word.strip()]
        frases = frases_de_palavras(palavras)
        progresso('Selecionando explicações completas e temas da pauta.')
        cortes = selecionar(frases,brief,quantidade)
        if not cortes:
            raise ValueError('Não há trecho falado completo de 35 a 58 segundos.')
        legendas(trabalho,palavras)
        gravar(trabalho/'plano.json',dict(video=str(video.relative_to(ROOT)),
                                          canal=canal,cortes=cortes,brief=brief))
        creditos = f'Gravação própria via OBS Studio · {marca["handle"]}'
        if origem:
            creditos = f'Fonte autorizada para edição · {origem}'
        arquivos, falhas = [], []
        (ROOT/'tmp').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT/'tmp',prefix='tech-') as temp:
            for numero,corte in enumerate(cortes,1):
                progresso(f'Renderizando corte {numero} de {len(cortes)}.')
                try:
                    with tempfile.TemporaryDirectory(dir=temp) as trecho:
                        renderizar(video,Path(trecho),marca,corte,numero,creditos,
                                   tem_audio,watermark,canal)
                        for arquivo in Path(trecho).iterdir():
                            shutil.move(str(arquivo),destino/arquivo.name)
                    arquivos.append(str((destino/f'corte_{numero:02d}.mp4').relative_to(ROOT)))
                    if pronto:
                        pronto(arquivos[-1])
                except (ValueError,OSError,subprocess.CalledProcessError):
                    logger.exception('Falha em %s, corte %s',video.name,numero)
                    falhas.append(numero)
        if not arquivos:
            raise ValueError(f'Nenhum corte renderizado. Confira logs/{canal}.log.')
        return dict(arquivos=arquivos,falhas=falhas,cortes=cortes,
                    destino=str(destino.relative_to(ROOT)),
                    transcript=str((trabalho/'palavras.json').relative_to(ROOT)),
                    srt=str((trabalho/'legendas.srt').relative_to(ROOT)))
    except Exception:
        logger.exception('Falha no lote %s de %s',canal,video.name)
        raise

"""Produção local de cortes verticais com revisão entre análise e render."""
import argparse
import json
import math
import os
import re
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CANAIS = ('games', 'ia', 'tecnologia')
REDES = ('youtube', 'instagram', 'tiktok')
GANCHOS = set('como porque porquê segredo melhor erro dica cuidado novo agora how why best mistake tip never'.split())
SINAIS_GAMES = set('missão assalto perseguição polícia policia fuga fugiu acidente bati bateu explosão explodiu explosao tiro tiros morreu npc roubou roubo caiu corrida perseguiu wanted wasted caramba nossa inacreditável inacreditavel'.split())


def ffmpeg(*args, cwd=ROOT):
    subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
                    '-filter_threads', '2', '-filter_complex_threads', '2',
                    *map(str, args)], cwd=cwd, check=True)


def gravar(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def analisar(args):
    from faster_whisper import WhisperModel

    video = args.video.resolve(strict=True)
    if not video.is_file() or not video.is_relative_to(ROOT / 'entrada'):
        raise ValueError('Coloque o vídeo local na pasta entrada/.')
    modelo = WhisperModel(str(args.modelo.resolve(strict=True)), device='cpu',
                          compute_type='int8', cpu_threads=4, local_files_only=True)
    segments, info = modelo.transcribe(str(video), language=args.idioma,
                                     vad_filter=True, word_timestamps=True)
    frases = [[{'inicio': round(w.start, 3), 'fim': round(w.end, 3), 'texto': w.word.strip()}
               for w in s.words or [] if w.end > w.start and w.word.strip()] for s in segments]
    frases = [f for f in frases if f]
    if not frases:
        raise ValueError('Nenhuma fala detectada. Confira o áudio e o idioma.')
    # Preserve the complete transcript independently of the short-form suggestions.
    transcricao = [w for frase in frases for w in frase]
    brief = args.brief.read_text(encoding='utf-8').strip() if args.brief else ''
    termos_brief = set(re.findall(r'\w+', brief.lower()))
    candidatos = []
    for i, frase in enumerate(frases):
        palavras = list(frase)
        for proxima in frases[i + 1:]:
            if palavras[-1]['fim'] - palavras[0]['inicio'] >= 18:
                break
            if (proxima[0]['inicio'] - palavras[-1]['fim'] > 6 or
                    proxima[-1]['fim'] - palavras[0]['inicio'] > 42):
                break
            palavras.extend(proxima)
        if palavras[-1]['fim'] - palavras[0]['inicio'] > 42:
            palavras = [w for w in palavras if w['fim'] <= palavras[0]['inicio'] + 42]
        if not palavras:
            continue
        inicio, fim = palavras[0]['inicio'], palavras[-1]['fim']
        termos = re.findall(r'\w+', ' '.join(w['texto'] for w in palavras).lower())
        ganchos = sorted(set(termos) & GANCHOS)
        coincidencias = sorted(set(termos) & termos_brief)
        sinais_games = sorted(set(termos) & SINAIS_GAMES) if args.canal == 'games' else []
        # This is a transparent heuristic; a human still chooses and reviews clips.
        nota = (len(ganchos) * 2.5 + min(len(termos), 60) / 12
                + min(fim - inicio, 30) / 12 + len(coincidencias) * 1.5
                + len(sinais_games) * 2)
        candidatos.append(dict(inicio=inicio, fim=fim, palavras=palavras,
                               pontuacao=round(nota, 2), ganchos=ganchos,
                               temas_encontrados=coincidencias,
                               sinais_games=sinais_games))
    cortes = []
    for corte in sorted(candidatos, key=lambda c: -c['pontuacao']):
        if any(min(corte['fim'], c['fim']) > max(corte['inicio'], c['inicio']) for c in cortes):
            continue
        cortes.append(corte)
        if len(cortes) == args.quantidade:
            break
    saida = ROOT / 'trabalho' / args.canal / f'{video.stem}.json'
    saida.parent.mkdir(parents=True, exist_ok=True)
    if saida.exists():
        raise ValueError(f'Plano já existe: {saida}. Renomeie-o para preservar sua revisão.')
    gravar(saida, dict(video=str(video.relative_to(ROOT)), canal=args.canal,
                      idioma=info.language, duracao_segundos=round(info.duration, 2),
                      modelo=str(args.modelo.resolve()), brief=brief,
                      transcricao=transcricao, cortes=cortes))
    transcricao_txt = '\n'.join(
        f"[{tempo(w['inicio'])}] {w['texto']}" for w in transcricao)
    saida.with_suffix('.txt').write_text(transcricao_txt + '\n', encoding='utf-8')
    saida.with_suffix('.srt').write_text('\n\n'.join(
        f"{i}\n{tempo(w['inicio'], True)} --> {tempo(w['fim'], True)}\n{w['texto']}"
        for i, w in enumerate(transcricao, 1)) + '\n', encoding='utf-8')
    print(saida)


def editar(corte, duration, pausa):
    palavras = sorted(corte['palavras'], key=lambda w: w['inicio'])
    intervalos = []
    for w in palavras:
        a, b = w['inicio'], w['fim']
        if not (0 <= a < b <= duration + .05) or not w['texto'].strip():
            raise ValueError('Palavra inválida no plano.')
        if intervalos and a - intervalos[-1][1] <= pausa:
            intervalos[-1][1] = max(b, intervalos[-1][1])
        else:
            intervalos.append([a, b])
    if not intervalos:
        raise ValueError('O corte está sem palavras.')
    ajustadas = []
    offset = 0
    indice = 0
    for a, b in intervalos:
        inicio, fim = max(0, a - .12), min(duration, b + .12)
        while indice < len(palavras) and palavras[indice]['inicio'] < b:
            w = palavras[indice]
            ajustadas.append(dict(texto=w['texto'], inicio=offset + w['inicio'] - inicio,
                                  fim=offset + min(fim, w['fim']) - inicio))
            indice += 1
        offset += fim - inicio
    return [(max(0, a - .12), min(duration, b + .12)) for a, b in intervalos], ajustadas


def tempo(seconds, srt=False):
    factor = 1000 if srt else 100
    total = max(0, round(seconds * factor))
    h, rest = divmod(total, 3600 * factor)
    m, rest = divmod(rest, 60 * factor)
    s, fraction = divmod(rest, factor)
    if srt:
        return f'{h:02}:{m:02}:{s:02},{fraction:03}'
    return f'{h}:{m:02}:{s:02}.{fraction:02}'


ASS = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,DejaVu Sans,66,&H00FFFFFF,&H00FFFFFF,&H00221B17,&H80000000,-1,0,0,0,100,100,0,0,1,5,3,2,110,110,340,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def legendas(pasta, palavras):
    srt, eventos = [], []
    for i in range(0, len(palavras), 4):
        grupo = palavras[i:i + 4]
        textos = [re.sub(r'[\r\n]+', ' ', w['texto']).strip() for w in grupo]
        a, b = grupo[0]['inicio'], max(w['fim'] for w in grupo)
        srt.append(f'{len(srt) + 1}\n{tempo(a, True)} --> {tempo(b, True)}\n' + ' '.join(textos))
        seguros = [t.translate(str.maketrans({'{': '｛', '}': '｝', '\\': '／'})) for t in textos]
        for j, w in enumerate(grupo):
            fim = grupo[j + 1]['inicio'] if j + 1 < len(grupo) else b
            if tempo(fim) <= tempo(w['inicio']):
                continue
            linha = seguros.copy()
            linha[j] = r'{\c&H93FF49&}' + linha[j] + r'{\c&HFFFFFF&}'
            eventos.append(f"Dialogue: 0,{tempo(w['inicio'])},{tempo(fim)},Default,,0,0,0,," + ' '.join(linha))
    (pasta / 'legendas.srt').write_text('\n\n'.join(srt) + '\n', encoding='utf-8')
    (pasta / 'legendas.ass').write_text(ASS + '\n'.join(eventos) + '\n', encoding='utf-8')
    gravar(pasta / 'palavras.json', palavras)


def renderizar(args):
    plano = json.loads(args.plano.read_text(encoding='utf-8'))
    canal = plano['canal']
    if canal not in CANAIS or args.corte < 1 or not .3 <= args.pausa <= 10:
        raise ValueError('Canal, número do corte ou limite de pausa inválido.')
    if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', args.slug):
        raise ValueError('Use um identificador com letras minúsculas, números e hífens.')
    video = (ROOT / plano['video']).resolve(strict=True)
    if not video.is_file() or not video.is_relative_to(ROOT / 'entrada'):
        raise ValueError('O vídeo precisa estar em entrada/.')
    destino = (ROOT / 'trabalho' / 'previas' / canal / args.slug if args.previa else
               ROOT / 'publicacoes' / canal / args.rede / args.slug)
    if destino.exists():
        raise ValueError(f'Publicação já existe: {destino}')
    duration = float(subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries',
                                             'format=duration', '-of', 'csv=p=0', str(video)]))
    corte = plano['cortes'][args.corte - 1]
    intervalos, palavras = editar(corte, duration, args.pausa)
    destino.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destino.parent, prefix='.render-') as temp:
        pasta = Path(temp)
        legendas(pasta, palavras)
        lista = []
        for i, (a, b) in enumerate(intervalos):
            nome = f'parte-{i}.mp4'
            if args.enquadramento == 'central':
                vf = 'scale=1080:1920:force_original_aspect_ratio=increase:force_divisible_by=2,crop=1080:1920'
            else:
                vf = ('scale=1080:1920:force_original_aspect_ratio=decrease:force_divisible_by=2,'
                      'pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=0x121824')
            ffmpeg('-ss', f'{a:.6f}', '-i', video, '-t', f'{b-a:.6f}', '-map', '0:v:0',
                   '-map', '0:a:0', '-vf', vf + ',setsar=1,fps=30', '-c:v', 'libx264',
                   '-preset', 'veryfast', '-crf', '18', '-pix_fmt', 'yuv420p',
                   '-c:a', 'aac', '-ar', '48000', '-ac', '2', '-threads', '4', nome, cwd=pasta)
            lista.append(f"file '{nome}'\n")
        (pasta / 'partes.txt').write_text(''.join(lista), encoding='utf-8')
        if args.motor == 'remotion':
            midia = pasta / 'midia'
            midia.mkdir()
            ffmpeg('-f', 'concat', '-safe', '1', '-i', 'partes.txt', '-c', 'copy',
                   'midia/base.mp4', cwd=pasta)
            duracao = float(subprocess.check_output(
                ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                 '-of', 'csv=p=0', str(midia / 'base.mp4')]))
            props = pasta / 'props.json'
            gravar(props, dict(frames=math.ceil(duracao * 30), words=[
                dict(word=w['texto'], startMs=round(w['inicio'] * 1000),
                     endMs=round(w['fim'] * 1000)) for w in palavras]))
            navegador = [f'--browser-executable={args.navegador.resolve()}'] if args.navegador else []
            subprocess.run(
                [str(ROOT / 'editor/node_modules/.bin/remotion'), 'render', 'src/CortesIA.tsx',
                 'CortesIA', str(pasta / 'video.mp4'), f'--props={props}',
                 f'--public-dir={midia}', '--concurrency=2', *navegador],
                cwd=ROOT / 'editor', check=True,
                env={**os.environ, 'TMPDIR': str(ROOT / 'tmp'),
                     'XDG_CACHE_HOME': str(ROOT / 'cache')})
            (midia / 'base.mp4').unlink()
            midia.rmdir()
            props.unlink()
        else:
            ffmpeg('-f', 'concat', '-safe', '1', '-i', 'partes.txt', '-vf', 'ass=legendas.ass',
                   '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '19', '-threads', '4',
                   '-c:a', 'aac', '-b:a', '160k', '-movflags', '+faststart', 'video.mp4', cwd=pasta)
        ffmpeg('-ss', str(min(1, sum(b - a for a, b in intervalos) / 2)), '-i', 'video.mp4',
               '-frames:v', '1', '-update', '1', '-q:v', '2', 'capa.jpg', cwd=pasta)
        titulo = args.titulo or (' '.join(w['texto'] for w in palavras[:9]).rstrip(',.!?') + ' | Corte')
        descricao = args.descricao or ' '.join(w['texto'] for w in palavras[:32])
        tags = {'games': '#Games #Gameplay', 'ia': '#InteligenciaArtificial #IA',
                'tecnologia': '#Tecnologia #Tech'}
        for nome, texto in [('titulo', titulo), ('descricao', descricao),
                            ('hashtags', args.hashtags or tags[canal]), ('creditos', args.creditos)]:
            (pasta / f'{nome}.txt').write_text(texto.strip() + '\n', encoding='utf-8')
        gravar(pasta / 'edicao.json', dict(origem=plano['video'], corte=args.corte,
                                          intervalos=intervalos, enquadramento=args.enquadramento, motor=args.motor))
        for i in range(len(lista)):
            (pasta / f'parte-{i}.mp4').unlink()
        (pasta / 'partes.txt').unlink()
        pasta.rename(destino)
    print(destino)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(required=True)
    analise = sub.add_parser('analisar')
    analise.add_argument('video', type=Path)
    analise.add_argument('--canal', choices=CANAIS, required=True)
    analise.add_argument('--modelo', type=Path, default=ROOT / 'cache/models/small')
    analise.add_argument('--idioma', default=None)
    analise.add_argument('--brief', type=Path, help='Pauta/referência textual para priorizar termos relevantes.')
    analise.add_argument('--quantidade', type=int, choices=range(1, 11), default=3)
    analise.set_defaults(func=analisar)
    render = sub.add_parser('renderizar')
    render.add_argument('plano', type=Path)
    render.add_argument('--corte', type=int, default=1)
    render.add_argument('--rede', choices=REDES, default='instagram')
    render.add_argument('--previa', action='store_true')
    render.add_argument('--slug', required=True)
    render.add_argument('--creditos', required=True)
    render.add_argument('--titulo')
    render.add_argument('--descricao')
    render.add_argument('--hashtags')
    render.add_argument('--pausa', type=float, default=.8)
    render.add_argument('--enquadramento', choices=('inteiro', 'central'), default='inteiro')
    render.add_argument('--motor', choices=('ffmpeg', 'remotion'), default='ffmpeg')
    render.add_argument('--navegador', type=Path)
    render.set_defaults(func=renderizar)
    args = parser.parse_args()
    try:
        args.func(args)
    except (OSError, ValueError, KeyError, IndexError, RuntimeError, subprocess.CalledProcessError) as error:
        parser.exit(1, f'Erro: {error}\n')


if __name__ == '__main__':
    main()

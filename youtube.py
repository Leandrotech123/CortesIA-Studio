"""Importação manual de um único vídeo do YouTube para a fila local."""
import json
from pathlib import Path
import shutil
import re
import subprocess
import sys
from urllib.parse import urlsplit, parse_qs

VIDEO_ID = re.compile(r'[A-Za-z0-9_-]{11}')


def normalizar(link):
    try:
        url = urlsplit(link.strip())
        if url.scheme not in ('http', 'https') or url.username or url.password or url.port is not None:
            raise ValueError()
        if url.hostname == 'youtu.be':
            video_id = url.path.strip('/')
        elif url.hostname in ('youtube.com', 'www.youtube.com', 'm.youtube.com'):
            if url.path == '/watch':
                video_id = parse_qs(url.query).get('v', [''])[0]
            elif re.fullmatch(r'/(shorts|live)/[^/]+/?', url.path):
                video_id = url.path.strip('/').split('/')[1]
            else:
                raise ValueError()
        else:
            raise ValueError()
        if VIDEO_ID.fullmatch(video_id):
            return f'https://www.youtube.com/watch?v={video_id}'
    except ValueError:
        pass
    raise ValueError('Cole o link de um único vídeo do YouTube.')


def baixar(link, pasta):
    url = normalizar(link)
    base = [sys.executable, '-m', 'yt_dlp', '--ignore-config', '--no-playlist',
            '--socket-timeout', '20', '--retries', '2']
    node = shutil.which('node')
    if not node:
        node = next((str(p) for p in sorted(Path.home().glob('.nvm/versions/node/*/bin/node'), reverse=True)
                     if p.is_file()), None)
    if node:
        base += ['--js-runtimes', f'node:{node}']
    consulta = subprocess.run([*base, '--skip-download', '--dump-single-json', '--', url],
                             capture_output=True, text=True, timeout=120)
    if consulta.returncode:
        raise ValueError('O YouTube não disponibilizou o vídeo. Confira o link ou envie o arquivo original.')
    dados = json.loads(consulta.stdout)
    if dados.get('live_status') in ('is_live', 'is_upcoming'):
        raise ValueError('Esta transmissão ainda está ao vivo ou agendada. Use o mesmo link depois que o YouTube disponibilizar a gravação.')
    if dados.get('live_status') == 'post_live':
        raise ValueError('O YouTube ainda está processando a gravação da live. Tente novamente quando ela estiver disponível.')
    duracao = dados.get('duration')
    if duracao is not None and duracao > 14400:
        raise ValueError('O vídeo tem mais de 4 horas. Envie um trecho menor como arquivo.')
    pasta.mkdir(parents=True, exist_ok=False)
    args = [*base, '--quiet', '--no-warnings', '--match-filters', '!is_live & duration <= 14400',
            '--max-filesize', '10G', '-f', 'bv[height<=1080]+ba/b[height<=1080]',
            '--merge-output-format', 'mkv', '-o', str(pasta / 'fonte.%(ext)s'), '--', url]
    result = subprocess.run(args, capture_output=True, text=True, timeout=3600)
    arquivos = [p for p in pasta.glob('fonte.*') if p.suffix in ('.mkv', '.mp4', '.webm')]
    if result.returncode or len(arquivos) != 1:
        detalhe = result.stderr.strip().splitlines()[-1:] or ['Vídeo indisponível ou fora dos limites da importação.']
        raise ValueError('Importação falhou. ' + detalhe[0][:400] + ' Se tiver o original, envie o arquivo.')
    return arquivos[0]

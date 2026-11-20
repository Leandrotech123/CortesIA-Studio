"""Importação manual de um único vídeo do YouTube para a fila local."""
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
    pasta.mkdir(parents=True, exist_ok=False)
    destino = pasta / 'fonte.%(ext)s'
    args = [sys.executable, '-m', 'yt_dlp', '--ignore-config', '--no-playlist',
            '--quiet', '--no-warnings', '--socket-timeout', '20', '--retries', '2',
            '--match-filters', '!is_live & duration <= 14400',
            '--max-filesize', '10G', '-f', 'bv[height<=1080]+ba/b[height<=1080]',
            '--merge-output-format', 'mkv', '-o', str(destino), '--', normalizar(link)]
    node = shutil.which('node')
    if not node:
        node = next((str(p) for p in sorted(Path.home().glob('.nvm/versions/node/*/bin/node'), reverse=True)
                     if p.is_file()), None)
    if node:
        args[3:3] = ['--js-runtimes', f'node:{node}']
    result = subprocess.run(args, capture_output=True, text=True, timeout=3600)
    arquivos = [p for p in pasta.glob('fonte.*') if p.suffix in ('.mkv', '.mp4', '.webm')]
    if result.returncode or len(arquivos) != 1:
        detalhe = result.stderr.strip().splitlines()[-1:] or ['Vídeo indisponível ou fora dos limites da importação.']
        raise ValueError('Importação falhou. ' + detalhe[0][:400] + ' Se tiver o original, envie o arquivo.')
    return arquivos[0]

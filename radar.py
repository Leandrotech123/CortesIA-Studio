"""Radar local: pesquisa metadados no YouTube sem baixar vídeos."""
from datetime import datetime
import json
import re
import subprocess
import sys
from zoneinfo import ZoneInfo

from youtube import normalizar

PILARES = {
    'games': (
        ('Choque gráfico e realismo', 'GTA VI gameplay graphics realism details', 'GTA VI gameplay gráficos realismo detalhes'),
        ('Caos e momentos épicos', 'gameplay police chase unexpected moments', 'gameplay perseguição polícia momentos épicos'),
        ('Curiosidades e segredos', 'game easter eggs hidden details', 'jogo easter eggs segredos detalhes ocultos'),
        ('Tutoriais e dicas', 'gameplay tips tutorial mission guide', 'dicas gameplay tutorial missão guia'),
        ('História e missões', 'game story missions gameplay', 'jogo história missões gameplay'),
    ),
    'ia': (
        ('Achados do GitHub', 'github open source free useful tools', 'github ferramentas gratuitas código aberto'),
        ('Automação de processos', 'workflow automation n8n business tutorial', 'automação processos n8n tutorial negócios'),
        ('IA para negócios', 'AI tools business productivity tutorial', 'IA ferramentas negócios produtividade tutorial'),
        ('Antes e depois', 'AI before after workflow demo', 'IA antes depois demonstração ferramenta'),
        ('Novidades tech', 'technology AI updates new tools demo', 'tecnologia IA novidades ferramentas demonstração'),
    ),
}


def buscar(nicho, regiao, tema='', progresso=None, executar=subprocess.run):
    if nicho not in PILARES or regiao not in ('br', 'en', 'ambos'):
        raise ValueError('Nicho ou região inválidos.')
    tema = ' '.join(str(tema).split())[:80]
    if re.search(r'[\x00-\x1f]', tema):
        raise ValueError('Tema inválido.')
    locales = ('br', 'en') if regiao == 'ambos' else (regiao,)
    encontrados, falhas, ids = [], [], set()
    for locale in locales:
        for pilar, query_en, query_br in PILARES[nicho]:
            if progresso:
                progresso(f'Buscando {pilar} ({locale.upper()})...')
            consulta = ' '.join(x for x in (tema, query_br if locale == 'br' else query_en) if x)
            cmd = [sys.executable, '-m', 'yt_dlp', '--ignore-config', '--flat-playlist',
                   '--dump-single-json', '--skip-download', '--no-warnings',
                   '--socket-timeout', '15', '--retries', '1', '--playlist-end', '3',
                   '--', 'ytsearch3:' + consulta]
            try:
                run = executar(cmd, capture_output=True, text=True, timeout=55)
                if run.returncode:
                    raise ValueError((run.stderr or 'Busca indisponível').strip().splitlines()[-1][:220])
                dados = json.loads(run.stdout)
                opcoes = []
                for item in dados.get('entries') or []:
                    if not item or item.get('live_status') in ('is_live', 'is_upcoming'):
                        continue
                    try:
                        link = normalizar(item.get('webpage_url') or
                                         'https://www.youtube.com/watch?v=' + item['id'])
                    except (ValueError, KeyError):
                        continue
                    if link in ids:
                        continue
                    duracao = item.get('duration')
                    if duracao is not None and not 35 <= duracao <= 14400:
                        continue
                    data = item.get('upload_date') or ''
                    visualizacoes = item.get('view_count') or 0
                    opcoes.append((data, visualizacoes, item, link))
                if not opcoes:
                    continue
                # Metadados flat podem omitir data e visualizações; não inferir popularidade.
                data, views, item, link = max(opcoes, key=lambda x: (x[0], x[1]))
                ids.add(link)
                encontrados.append(dict(
                    titulo=item.get('title') or 'Sem título',
                    canal=item.get('channel') or item.get('uploader') or 'Fonte não informada',
                    duracao=item.get('duration'), pilar=pilar, link=link,
                    regiao=locale, data=data or None, visualizacoes=views or None))
            except (OSError, ValueError, json.JSONDecodeError, subprocess.TimeoutExpired) as error:
                falhas.append(f'{pilar} ({locale.upper()}): {error}')
    if not encontrados and falhas:
        raise ValueError('A busca não retornou vídeos. ' + falhas[0])
    return dict(resultados=encontrados[:10], avisos=falhas,
                consultado_em=datetime.now(ZoneInfo('America/Fortaleza')).isoformat())

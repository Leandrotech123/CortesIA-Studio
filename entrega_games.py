"""Entrega local de um corte Games depois da aprovação no painel."""
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory

from cortes import REDES, ROOT

ARQUIVOS = {
    '.mp4': 'video.mp4', '_capa.jpg': 'capa.jpg', '_legendas.srt': 'legendas.srt',
    '_legendas.ass': 'legendas.ass', '_palavras.json': 'palavras.json',
    '_meta.json': 'meta.json',
}
ROTULOS = {'tiktok': 'TikTok', 'youtube': 'YouTube Shorts', 'instagram': 'Instagram Reels'}


def entregar(origem, redes):
    corte = (ROOT / origem).resolve(strict=True)
    base = ROOT / 'publicacoes/games'
    if corte.parent.parent != base or not corte.is_file() or corte.suffix != '.mp4':
        raise ValueError('Selecione um corte do lote Games.')
    if not redes or any(rede not in REDES for rede in redes):
        raise ValueError('Selecione pelo menos uma plataforma válida.')
    meta = json.loads(corte.with_name(corte.stem + '_meta.json').read_text(encoding='utf-8'))
    entregas = {}
    for rede in dict.fromkeys(redes):
        pasta = base / rede
        pasta.mkdir(exist_ok=True)
        destino = pasta / f'{corte.parent.name}_{corte.stem}'
        if not destino.exists():
            with TemporaryDirectory(dir=pasta, prefix='.entrega-') as temp:
                pacote = Path(temp)
                for sufixo, nome in ARQUIVOS.items():
                    shutil.copyfile(corte.with_name(corte.stem + sufixo), pacote / nome)
                (pacote / 'publicar.txt').write_text(meta['redes'][ROTULOS[rede]] + '\n', encoding='utf-8')
                (pacote / 'creditos.txt').write_text(meta['creditos'] + '\n', encoding='utf-8')
                pacote.rename(destino)
        entregas[rede] = str(destino.relative_to(ROOT))
    return entregas

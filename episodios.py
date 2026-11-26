"""Título editorial, guia cronológico e arquivos de narração revisáveis."""
import json
from pathlib import Path
import re

from cortes import ffmpeg, gravar


def manchete(canal, palavras, tema=''):
    contexto = ' '.join(w['texto'] for w in palavras).casefold()
    if canal == 'games':
        regras = (
            (r'persegui|polic|fuga|chase', 'UMA PERSEGUIÇÃO CHEIA DE TENSÃO'),
            (r'miss[aã]o|mission', 'UM MOMENTO CHAVE DA MISSÃO'),
            (r'gr[aá]fic|visual|realism', 'DETALHES VISUAIS DO JOGO'),
            (r'segredo|easter|hidden', 'UM DETALHE ESCONDIDO NO JOGO'),
            (r'dica|tutorial|como passar', 'DICA PARA AVANÇAR NO JOGO'),
        )
        padrao = 'UM MOMENTO DO JOGO EM FOCO'
    else:
        regras = (
            (r'github|reposit[oó]rio|open.source', 'UMA FERRAMENTA PARA CONHECER'),
            (r'automa|n8n|workflow', 'AUTOMAÇÃO PARA POUPAR TEMPO'),
            (r'neg[oó]cio|venda|empresa', 'TECNOLOGIA APLICADA A NEGÓCIOS'),
            (r'antes|depois|before|after', 'VEJA A DIFERENÇA NA PRÁTICA'),
            (r'\bia\b|intelig[eê]ncia artificial|\bai\b', 'IA APLICADA AO DIA A DIA'),
        )
        padrao = 'O QUE VALE OBSERVAR AQUI'
    titulo = next((texto for padrao_re, texto in regras if re.search(padrao_re, contexto)), padrao)
    assert len(titulo) <= 42 and 4 <= len(titulo.split()) <= 7
    return titulo


def ato_do_corte(inicio, duracao):
    proporcao = inicio / max(duracao, 1)
    return ('COMEÇO' if proporcao < 1/3 else
            'MEIO' if proporcao < 2/3 else 'FIM')


def roteiro(canal, titulo, palavras, duracao, creditos, idioma='pt', nome='corte'):
    fim = max(1, round(duracao))
    desenvolvimento_fim = min(40, max(5, fim - 8))
    trecho = ' '.join(w['texto'] for w in palavras).strip()
    if idioma and idioma.lower().startswith('pt'):
        # A transcrição é matéria-prima, não um resumo factual verificado.
        desenvolvimento = ('Ponto de partida da fala original, para reescrever com sua voz: '
                           + trecho[:750])
        revisao = 'Revise nomes, fatos e o que aparece na tela antes de gravar.'
    else:
        desenvolvimento = ('[Descreva em português a ação ou ferramenta mostrada após assistir '
                           f'ao trecho. A transcrição original está em {nome}_palavras.json: '
                           + trecho[:450] + ']')
        revisao = ('A fala original não está em português. Tradução e descrição visual '
                   'precisam de revisão humana.')
    gancho = ('O que acontece neste trecho?' if canal == 'games' else
              'O que este trecho mostra na prática?')
    cta = ('Qual parte você quer ver no próximo episódio? Comente.' if canal == 'games'
           else 'Você usaria isso no seu dia a dia? Salve e comente.')
    return (f'TÍTULO DA CENA: {titulo}\n'
            f'IDIOMA DA FONTE: {idioma or "não identificado"}\n'
            f'[{0:02}s - {min(4,fim):02}s] GANCHO: {gancho}\n'
            f'[04s - {desenvolvimento_fim:02}s] DESENVOLVIMENTO: {desenvolvimento}\n'
            f'[{desenvolvimento_fim:02}s - {fim:02}s] FECHAMENTO & CTA: {cta}\n'
            f'CRÉDITOS: {creditos}\n'
            f'REVISÃO: {revisao}\n')


def preparar(pasta, nome, canal, corte, numero, duracao_total, creditos,
             idioma='pt', tema=''):
    pasta = Path(pasta).resolve()
    titulo = manchete(canal, corte['palavras'], tema)
    ato = ato_do_corte(corte['inicio'], duracao_total)
    texto = roteiro(canal, titulo, corte['palavras'], corte['fim']-corte['inicio'],
                    creditos, idioma, nome)
    (pasta / (nome+'_roteiro.txt')).write_text(texto, encoding='utf-8')
    fonte = pasta / (nome+'.mp4')
    base = pasta / (nome+'_base_narracao.mp4')
    ffmpeg('-i', fonte, '-map', '0:v:0', '-an', '-c:v', 'copy',
           '-movflags', '+faststart', base, cwd=pasta)
    meta_path = pasta / (nome+'_meta.json')
    meta = json.loads(meta_path.read_text(encoding='utf-8'))
    meta.update(titulo=titulo, episodio=numero, ato=ato, roteiro=texto,
                base_narracao=base.name, idioma_fonte=idioma,
                roteiro_requer_revisao=True)
    gravar(meta_path, meta)
    return titulo, ato


def guia(pasta, episodios):
    linhas = ['GUIA DE EPISÓDIOS — ORDEM CRONOLÓGICA',
              'A divisão começo/meio/fim usa a posição no vídeo; revise a narrativa antes de publicar.', '']
    for ep in episodios:
        linhas.append(f"PARTE {ep['numero']:02d} · {ep['ato']} · {ep['nome']}.mp4")
        linhas.append(f"Origem: {ep['inicio']:.1f}s–{ep['fim']:.1f}s · {ep['titulo']}")
        linhas.append('')
    (Path(pasta)/'guia_episodios.txt').write_text('\n'.join(linhas),encoding='utf-8')

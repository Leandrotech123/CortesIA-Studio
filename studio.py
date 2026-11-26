"""Painel local simples para preparar gravações, analisar e renderizar cortes."""
import json
import logging
import mimetypes
import re
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4
from youtube import baixar, normalizar
from radar import buscar as buscar_radar

from cortes import CANAIS, ROOT
from games import processar as processar_games
from tech import processar as processar_tech
from entrega_games import entregar as entregar_games

STATE = ROOT / '.studio'
RADAR_STATE = STATE / 'radar'
LOCK = threading.Lock()
JOBS = ThreadPoolExecutor(max_workers=1, thread_name_prefix='cortesia')
BUSCAS = ThreadPoolExecutor(max_workers=2, thread_name_prefix='radar')
EXTENSOES = {'.mp4', '.mov', '.mkv', '.webm', '.m4v'}
REF_EXTENSOES = EXTENSOES | {'.png', '.jpg', '.jpeg', '.webp', '.pdf', '.txt'}
PAGE = r'''<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>CortesIA Studio</title>
<style>
:root{font:16px system-ui;color:#eee;background:#10131a}body{max-width:1050px;margin:35px auto;padding:0 18px}h1{font-size:2rem}p{color:#b8c0cf}.grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}.card{background:#1a202b;border:1px solid #303949;border-radius:14px;padding:20px;margin:16px 0}label{display:block;margin:12px 0 5px}input,textarea,select,button{font:inherit;padding:10px;border-radius:8px;border:1px solid #465267;background:#121722;color:#fff;width:100%;box-sizing:border-box}textarea{min-height:100px}button{background:#61d6b0;color:#10211c;font-weight:700;cursor:pointer;margin-top:12px}.job{border-top:1px solid #394253;padding:14px 0}.candidate{background:#121722;padding:12px;border-radius:8px;margin:8px 0}.small{font-size:.86rem;color:#b8c0cf}a{color:#74dcbc}.abas{display:flex;gap:8px;flex-wrap:wrap}.abas button{width:auto}.aba[hidden]{display:none}.radar-result{border-top:1px solid #394253;padding:14px 0}.radar-result select{max-width:240px}@media(max-width:700px){.grid{grid-template-columns:1fr}}
</style><body><h1>CortesIA Studio</h1><p>Seu espaço local para enviar gravações, guardar referências e preparar cortes revisáveis. Os arquivos ficam neste computador.</p>
<nav class="abas" aria-label="Modos de trabalho"><button id="tab-envio" onclick="mostrarAba('envio')">1. Enviar Gravação Local</button><button id="tab-radar" onclick="mostrarAba('radar')">2. Radar Diário</button></nav>
<div id="aba-envio" class="aba"><div class="grid"><section class="card"><h2>Novo vídeo</h2><label>Link de um vídeo do YouTube</label><input id="youtube" type="url" placeholder="https://www.youtube.com/watch?v=…"><label><input id="youtubePermitido" type="checkbox" style="width:auto"> Posso baixar e editar este vídeo</label><label>Ou envie o arquivo gravado</label><input id="video" type="file" accept="video/*"><label>Vídeo ou imagem de referência (opcional)</label><input id="reference" type="file" accept="video/*,image/*,.pdf,.txt"><label>Canal</label><select id="channel"><option value="games">Games</option><option value="ia">IA</option><option value="tecnologia">Tecnologia</option></select><label>Referências, pauta e instruções</label><textarea id="brief" placeholder="Cole links e descreva ritmo, estilo, temas, público, idioma e o que evitar. Separe fatos e opinião."></textarea><label>Quantidade de sugestões</label><select id="quantity"><option>3</option><option>5</option><option>8</option><option>10</option></select><label><input id="serie" type="checkbox" style="width:auto"> Série curta: episódios de 35 a 58 segundos em ordem cronológica</label><button onclick="startJob()">Enviar e analisar</button><div id="message" class="small"></div></section>
<section class="card"><h2>Como usar referências</h2><p>O arquivo de referência fica separado do vídeo que será cortado e não é publicado nem usado como fonte automática de fatos. Descreva no brief o estilo que quer aproveitar. O sistema usa os termos escritos para ordenar sugestões.</p><p>Envie somente gravações suas ou com autorização. Antes de publicar, confira cortes, legendas, créditos e regras da plataforma.</p><p>Em Games, o Studio analisa a gravação própria e exporta automaticamente trechos de 1min30s a 2min, com arquivos e textos para postar. Confira as prévias antes de publicar nas redes.</p><p>Em IA e Tecnologia, o Studio exporta explicações de 35 a 58 segundos mantendo a tela inteira, com identidade da marca configurada. Revise as prévias e aprove por rede.</p><p>Para gravações longas, mantenha o computador ligado e aguarde a análise local terminar.</p></section></div></div>
<div id="aba-radar" class="aba" hidden><section class="card"><h2>Radar &amp; busca na internet</h2>
<p>Pesquise referências sem baixar vídeos. O idioma da busca não confirma o idioma do vídeo; confira a fonte. Para processar um resultado, escolha a fonte e confirme que possui direito de baixar e editar.</p>
<label>Nicho / marca</label><select id="radar-nicho"><option value="games">Games</option><option value="ia">IA &amp; Tecnologia</option></select>
<label>Região / idioma</label><select id="radar-regiao"><option value="br">Busca em português (BR)</option><option value="en">Busca em inglês (EN)</option><option value="ambos">Ambos (PT + EN)</option></select>
<label>Filtro / jogo / tema específico</label><input id="radar-tema" maxlength="80" placeholder="GTA VI, GitHub, automação n8n">
<button onclick="buscarSugestoes()">Buscar Sugestões Diárias (5 Pilares Virais)</button>
<div id="radar-status" class="small" aria-live="polite"></div><div id="radar-results"></div>
</section></div>
<section class="card"><h2>Trabalhos e cortes</h2><div id="jobs">Carregando…</div></section>
<script>
async function startJob(){
  const f=document.querySelector('#video').files[0], link=document.querySelector('#youtube').value.trim();
  const msg=document.querySelector('#message');
  if(Boolean(f)===Boolean(link)){msg.textContent='Escolha um arquivo ou cole um link.';return}
  const autorizado=document.querySelector('#youtubePermitido').checked;
  if(link && !autorizado){msg.textContent='Confirme que pode baixar e editar este vídeo.';return}
  const data={channel:document.querySelector('#channel').value,brief:document.querySelector('#brief').value,
    quantity:Number(document.querySelector('#quantity').value),serie:document.querySelector('#serie').checked};
  async function enviar(file, tipo){
    const r=await fetch('/api/upload?kind='+tipo+'&name='+encodeURIComponent(file.name),{method:'PUT',body:file});
    const d=await r.json();
    if(!r.ok)throw new Error(d.error);
    return d.name;
  }
  try{
    const ref=document.querySelector('#reference').files[0];
    if(ref){msg.textContent='Salvando referência…';data.reference=await enviar(ref,'reference')}
    if(link){data.youtube=link;data.autorizado=autorizado}
    else{msg.textContent='Enviando arquivo…';data.video=await enviar(f,'video')}
    const r=await fetch('/api/analyze',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
    const d=await r.json();
    msg.textContent=r.ok?'Trabalho na fila. O progresso aparece abaixo.':d.error;
    if(r.ok)await refresh(true);
  }catch(error){msg.textContent=error.message}
}
async function render(video,corte,channel){let slug=prompt('Nome curto do corte (ex.: gta-vi-momento-1)');if(!slug)return;let credits=prompt('Créditos e autorização/origem:','Gravação própria');if(credits===null)return;let r=await fetch('/api/render',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({video,corte,channel,slug,credits})});let d=await r.json();if(r.ok){alert('Prévia pronta. Vou abrir o vídeo para revisão.');window.open('/media/'+encodeURIComponent(d.video),'_blank')}else alert(d.error);refresh()}
let snapshot=''; async function refresh(forcar=false){if(!forcar && document.querySelector('.candidate[open]'))return;let r=await fetch('/api/jobs');let d=await r.json();const atual=JSON.stringify(d);if(!forcar && atual===snapshot)return;snapshot=atual;const abertas=forcar?[...document.querySelectorAll('details[open] form')].map(f=>f.dataset.corte):[];document.querySelector('#jobs').innerHTML=d.jobs.length?d.jobs.map(j=>`<div class="job"><b>${esc(j.youtube||j.video)}</b> · ${esc(j.status)}<div class="small">${esc(j.message||'')}</div>${(j.arquivos||[]).map((f,i)=>painelCorte(j,f,i)).join('')}${j.reference?`<p class="small">Referência salva: <a href="/files/${encodeURIComponent(j.reference)}">${esc(j.reference)}</a></p>`:''}${j.brief?`<p class="small">Brief: ${esc(j.brief)}</p>`:''}${[].map((c,i)=>`<div class="candidate"><b>Sugestão ${i+1}</b> · ${Math.round(c.inicio)}s–${Math.round(c.fim)}s · score ${c.pontuacao}<p>${esc(c.palavras.map(w=>w.texto).join(' '))}</p><span class="small">Temas do brief: ${esc((c.temas_encontrados||[]).join(', ')||'nenhum termo literal')} · Pistas de gameplay: ${esc((c.sinais_games||[]).join(', ')||'nenhuma')}</span><button onclick="render('${esc(j.video)}',${i+1},'${esc(j.channel)}')">Gerar prévia deste corte</button></div>`).join('')}${j.transcript?`<p><a href="/files/${encodeURIComponent(j.transcript)}">Baixar transcrição completa</a> · <a href="/files/${encodeURIComponent(j.srt)}">Baixar transcrição (.srt)</a></p>`:''}</div>`).join(''):'Nenhum trabalho ainda.';document.querySelectorAll('details form').forEach(f=>{if(abertas.includes(f.dataset.corte))f.closest('details').open=true})}
const redes = {instagram:'Instagram Reels',youtube:'YouTube Shorts',tiktok:'TikTok'};
const media = p => '/media/' + encodeURIComponent(p);
const arquivo = p => '/files/' + encodeURIComponent(p);
function painelCorte(j,f,i){
  const links = j.entregas?.[f] || {};
  const prefixo = f.replace(/\.mp4$/, '');
  return `<details class="candidate"><summary>${j.episodios?.[i]?'Parte '+String(i+1).padStart(2,'0')+' · '+esc(j.episodios[i].titulo):'Corte '+(i+1)} · ${Object.keys(links).length ? 'Aprovado' : 'Para revisão'}</summary>
    <video controls preload="none" playsinline poster="${arquivo(prefixo+'_capa.jpg')}" style="max-width:240px;width:100%;margin:12px 0" data-src="${media(f)}"></video>
    <p><a href="${arquivo(prefixo+'_legendas.srt')}">Legendas SRT</a> · <a href="${arquivo(prefixo+'_palavras.json')}">Transcrição por palavra</a> · <a href="${arquivo(prefixo+'_publicar.txt')}">Textos para as redes</a></p>
    ${j.episodios?.length?`<p><a href="${arquivo(prefixo+'_roteiro.txt')}">Roteiro PT-BR revisável</a> · <a href="${arquivo(prefixo+'_base_narracao.mp4')}">Vídeo sem áudio para narrar</a> · <a href="${arquivo(f.substring(0,f.lastIndexOf('/'))+'/guia_episodios.txt')}">Guia de episódios</a></p>`:''}
    <form class="aprovar" data-job="${esc(j.video)}" data-corte="${esc(f)}">
      ${Object.entries(redes).map(([r,n])=>`<label style="display:inline-block;margin-right:14px"><input type="checkbox" name="redes" value="${r}" checked style="width:auto"> ${n}</label>`).join('')}
      <button>Aprovar e preparar arquivos</button><output aria-live="polite"></output>
    </form>
    ${Object.entries(links).map(([r,p])=>`<p><b>${redes[r]}</b> · <a href="${arquivo(p+'/video.mp4')}">Baixar vídeo</a> · <a href="${arquivo(p+'/legendas.srt')}">Legendas</a> · <a href="${arquivo(p+'/publicar.txt')}">Texto para postar</a> · <a href="${arquivo(p+'/capa.jpg')}">Capa</a></p>`).join('')}
  </details>`;
}
document.addEventListener('toggle', e=>{
  const video = e.target.querySelector?.('video[data-src]');
  if(e.target.open && video && !video.hasAttribute('src')) video.src=video.dataset.src;
},true);
document.addEventListener('submit',async e=>{
  if(!e.target.matches('.aprovar')) return;
  e.preventDefault();
  const form=e.target, button=form.querySelector('button'), out=form.querySelector('output');
  const escolhidas=new FormData(form).getAll('redes');
  if(!escolhidas.length){out.textContent='Selecione uma rede.';return}
  button.disabled=true;
  out.textContent='Preparando os arquivos…';
  try{
    const r=await fetch('/api/approve',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({video:form.dataset.job,corte:form.dataset.corte,redes:escolhidas})});
    const d=await r.json();
    if(!r.ok)throw new Error(d.error);
    await refresh(true);
  }catch(error){out.textContent=error.message}
  finally{button.disabled=false}
});
function mostrarAba(aba){
  for(const nome of ['envio','radar'])document.querySelector('#aba-'+nome).hidden=nome!==aba;
  document.querySelector('#tab-envio').setAttribute('aria-current',aba==='envio'?'page':'false');
  document.querySelector('#tab-radar').setAttribute('aria-current',aba==='radar'?'page':'false');
}
let radarId=null, radarItens=[];
async function buscarSugestoes(){
  const status=document.querySelector('#radar-status');
  status.textContent='Busca iniciada. Nenhum vídeo será baixado nesta etapa.';
  document.querySelector('#radar-results').innerHTML='';
  try{
    const r=await fetch('/api/radar/search',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({nicho:document.querySelector('#radar-nicho').value,
        regiao:document.querySelector('#radar-regiao').value,tema:document.querySelector('#radar-tema').value})});
    const d=await r.json();if(!r.ok)throw new Error(d.error);
    radarId=d.id;await acompanharRadar();
  }catch(e){status.textContent=e.message}
}
async function acompanharRadar(){
  if(!radarId)return;
  try{
    const r=await fetch('/api/radar/'+radarId);const d=await r.json();if(!r.ok)throw new Error(d.error);
    document.querySelector('#radar-status').textContent=d.message||d.status;
    if(d.status==='Buscando'){setTimeout(acompanharRadar,3000);return}
    radarItens=d.resultados||[];
    document.querySelector('#radar-results').innerHTML=radarItens.length?radarItens.map((v,i)=>`
      <article class="radar-result"><b>${esc(v.titulo)}</b><p class="small">
      ${esc(v.canal)} · ${v.duracao?Math.round(v.duracao/60)+' min':'Duração não informada'} ·
      ${esc(v.pilar)} · ${v.regiao==='br'?'Busca PT-BR':'Busca EN'}${v.data?' · '+esc(v.data):''}</p>
      <a href="${esc(v.link)}" target="_blank" rel="noopener noreferrer">Abrir fonte original</a>
      ${d.nicho==='ia'?'<label>Canal de destino</label><select id="radar-canal-'+i+'"><option value="ia">IA</option><option value="tecnologia">Tecnologia</option></select>':''}
      <label><input type="checkbox" id="radar-direito-${i}" style="width:auto">
      Tenho autorização para baixar e editar este vídeo</label>
      <button onclick="processarRadar(${i})">Baixar e gerar cortes + roteiro</button></article>`).join(''):'Nenhum resultado nesta busca.';
    if(d.avisos?.length)document.querySelector('#radar-status').textContent+=' Algumas consultas falharam; tente outro filtro se necessário.';
  }catch(e){document.querySelector('#radar-status').textContent=e.message}
}
async function processarRadar(i){
  const status=document.querySelector('#radar-status');
  if(!document.querySelector('#radar-direito-'+i).checked){status.textContent='Confirme seu direito de baixar e editar esta fonte.';return}
  const canal=document.querySelector('#radar-canal-'+i)?.value||'games';
  try{
    const r=await fetch('/api/radar/process',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({id:radarId,indice:i,canal,autorizado:true})});
    const d=await r.json();if(!r.ok)throw new Error(d.error);
    status.textContent='Vídeo escolhido. Download e processamento na fila; acompanhe em Trabalhos e cortes.';
    await refresh(true);
  }catch(e){status.textContent=e.message}
}
mostrarAba('envio');
function esc(s){return String(s||'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}refresh();setInterval(refresh,5000)
</script></body></html>'''


def safe_name(name, reference=False):
    name = Path(name).name
    stem = re.sub(r'[^\w.-]+', '-', Path(name).stem, flags=re.UNICODE).strip('.-')[:100]
    suffix = Path(name).suffix.lower()
    if not stem or suffix not in (REF_EXTENSOES if reference else EXTENSOES):
        raise ValueError('Formato não permitido para este tipo de arquivo.')
    return stem + suffix


def records():
    STATE.mkdir(exist_ok=True)
    return [json.loads(p.read_text(encoding='utf-8')) for p in sorted(STATE.glob('*.json'))]


def update(path, **values):
    data = json.loads(path.read_text(encoding='utf-8'))
    data.update(values)
    provisório = path.with_suffix('.tmp')
    provisório.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    provisório.replace(path)


def run_analysis(record, path, brief_path, channel, quantity, origem=None, serie=False):
    update(record, status='Analisando', message='Transcrição local em andamento. O tempo depende da duração e do processador.')
    if channel == 'games':
        try:
            resultado = processar_games(
                path, brief_path.read_text(encoding='utf-8'), quantity,
                lambda etapa: update(record, message=etapa), origem=origem, serie=serie)
            falhas = resultado['falhas']
            update(record, **resultado, status='Concluído com falhas' if falhas else 'Pronto para revisão',
                   message=f"{len(resultado['arquivos'])} corte(s) exportado(s). Confira áudio, legendas e enquadramento.")
        except Exception as error:
            logging.exception('Falha no processamento Games')
            update(record, status='Falhou', message=str(error))
        return
    try:
        resultado = processar_tech(
            path, brief_path.read_text(encoding='utf-8'), quantity, channel,
            lambda etapa: update(record, message=etapa), origem=origem)
        falhas = resultado['falhas']
        update(record, **resultado, status='Concluído com falhas' if falhas else 'Pronto para revisão',
               message=f"{len(resultado['arquivos'])} corte(s) de {channel} exportado(s). Revise antes de aprovar.")
    except Exception as error:
        logging.exception('Falha no processamento %s', channel)
        update(record, status='Falhou', message=str(error))


def importar_e_analisar(record, link, brief_path, channel, quantity, radar=False, serie=False):
    update(record, status='Analisando', message='Importando vídeo do YouTube…')
    try:
        pasta = ROOT / 'entrada' / ('radar' if radar else 'youtube') / record.stem
        arquivo = baixar(link, pasta, mp4=radar)
        video = arquivo.with_name(record.stem + arquivo.suffix)
        arquivo.rename(video)
        update(record, video=str(video.relative_to(ROOT)))
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        logging.exception('Falha na importação do YouTube')
        update(record, status='Falhou', message=str(error))
        return
    origem = link
    if radar:
        fonte = json.loads(record.read_text(encoding='utf-8'))
        origem = f"{fonte.get('source_channel', 'Fonte não informada')} · {link}"
    run_analysis(record, video, brief_path, channel, quantity, origem, serie=serie)


def executar_busca(record, nicho, regiao, tema):
    try:
        resultado = buscar_radar(nicho, regiao, tema,
                                lambda mensagem: update(record, message=mensagem))
        update(record, **resultado, status='Concluído',
               message=f"{len(resultado['resultados'])} referências encontradas; nenhum vídeo baixado.")
    except Exception as error:
        logging.exception('Falha na busca Radar')
        update(record, status='Falhou', message=str(error))


class Handler(BaseHTTPRequestHandler):
    server_version = 'CortesIAStudio/0.1'

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def origem_local(self):
        portas = {f'{nome}:{self.server.server_port}' for nome in ('localhost', '127.0.0.1')}
        host = self.headers.get('Host')
        origem = self.headers.get('Origin')
        if host in portas and (origem is None or origem == f'http://{host}'):
            return True
        self.send_json({'error': 'Abra o painel pelo endereço local.'}, 403)
        return False

    def do_GET(self):
        if not self.origem_local():
            return
        if self.path == '/health':
            self.send_json({'service': 'cortesia-studio'})
        elif self.path == '/':
            body = PAGE.encode()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == '/api/jobs':
            self.send_json({'jobs': records()})
        elif self.path.startswith('/api/radar/'):
            chave = self.path.removeprefix('/api/radar/')
            if not re.fullmatch(r'[a-f0-9]{12}', chave):
                self.send_json({'error': 'Busca inválida'}, 404)
                return
            registro = RADAR_STATE / (chave + '.json')
            if not registro.is_file():
                self.send_json({'error': 'Busca não encontrada'}, 404)
                return
            self.send_json(json.loads(registro.read_text(encoding='utf-8')))
        elif self.path.startswith('/files/'):
            name = urllib.parse.unquote(self.path.removeprefix('/files/'))
            target = (ROOT / name).resolve()
            if not (target.is_relative_to(ROOT / 'trabalho') or
                    (any(target.is_relative_to(ROOT / 'publicacoes' / c) for c in CANAIS) and
                     target.suffix in ('.txt', '.jpg', '.json', '.srt', '.ass', '.mp4'))) or not target.is_file():
                self.send_json({'error': 'Arquivo não encontrado'}, 404)
                return
            self.send_response(200)
            self.send_header('Content-Type', mimetypes.guess_type(target.name)[0] or 'application/octet-stream')
            self.send_header('Content-Disposition', f'attachment; filename="{target.name}"')
            self.send_header('Content-Length', str(target.stat().st_size))
            self.end_headers()
            try:
                with target.open('rb') as arquivo:
                    while chunk := arquivo.read(1024 * 1024):
                        self.wfile.write(chunk)
            except (BrokenPipeError, ConnectionResetError):
                pass
        elif self.path.startswith('/media/'):

            name = urllib.parse.unquote(self.path.removeprefix('/media/'))
            target = (ROOT / name).resolve()
            if not (target.is_relative_to(ROOT / 'trabalho/previas') or
                    any(target.is_relative_to(ROOT / 'publicacoes' / c) for c in CANAIS)) or not target.is_file() or target.suffix != '.mp4':
                self.send_json({'error': 'Prévia não encontrada'}, 404)
                return
            self.send_response(200)
            self.send_header('Content-Type', 'video/mp4')
            self.send_header('Content-Length', str(target.stat().st_size))
            self.send_header('Content-Disposition', f'inline; filename="{target.name}"')
            self.end_headers()
            with target.open('rb') as video:
                while chunk := video.read(1024 * 1024):
                    self.wfile.write(chunk)
        else:
            self.send_json({'error': 'Não encontrado'}, 404)

    def do_PUT(self):
        if not self.origem_local():
            return
        if not self.path.startswith('/api/upload?'):
            self.send_json({'error': 'Rota inválida'}, 404)
            return
        try:
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            kind = query.get('kind', ['video'])[0]
            name = safe_name(query.get('name', [''])[0], reference=kind == 'reference')
            length = int(self.headers.get('Content-Length', '0'))
            if length <= 0 or length > 20 * 1024**3:
                raise ValueError('O arquivo está vazio ou excede o limite de 20 GB.')
            channel_dir = ROOT / ('trabalho/referencias/midia' if kind == 'reference' else 'entrada/uploads')
            channel_dir.mkdir(parents=True, exist_ok=True)
            target = channel_dir / name
            if target.exists():
                raise ValueError('Já existe um arquivo com esse nome em entrada/uploads/. Renomeie o vídeo.')
            remaining = length
            with target.open('xb') as out:
                while remaining:
                    chunk = self.rfile.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise ValueError('Upload interrompido.')
                    out.write(chunk)
                    remaining -= len(chunk)
            self.send_json({'name': str(target.relative_to(ROOT))})
        except (ValueError, OSError) as error:
            self.send_json({'error': str(error)}, 400)

    def do_POST(self):
        if not self.origem_local():
            return
        try:
            size = int(self.headers.get('Content-Length', '0'))
            data = json.loads(self.rfile.read(size))
            if self.path == '/api/radar/search':
                nicho, regiao = data.get('nicho'), data.get('regiao')
                tema = str(data.get('tema', ''))[:80]
                if nicho not in ('games', 'ia') or regiao not in ('br', 'en', 'ambos'):
                    raise ValueError('Nicho ou região inválidos.')
                chave = uuid4().hex[:12]
                RADAR_STATE.mkdir(parents=True, exist_ok=True)
                registro = RADAR_STATE / (chave + '.json')
                registro.write_text(json.dumps(dict(id=chave, nicho=nicho, regiao=regiao,
                    tema=tema, status='Buscando', message='Iniciando busca...',
                    resultados=[], avisos=[]), ensure_ascii=False, indent=2), encoding='utf-8')
                BUSCAS.submit(executar_busca, registro, nicho, regiao, tema)
                self.send_json({'id': chave, 'status': 'Buscando'})
            elif self.path == '/api/radar/process':
                chave = str(data.get('id', ''))
                if not re.fullmatch(r'[a-f0-9]{12}', chave):
                    raise ValueError('Busca inválida.')
                registro = RADAR_STATE / (chave + '.json')
                busca = json.loads(registro.read_text(encoding='utf-8'))
                indice = data.get('indice')
                if type(indice) is not int or not 0 <= indice < len(busca.get('resultados', [])):
                    raise ValueError('Resultado inválido.')
                if busca.get('status') != 'Concluído' or data.get('autorizado') is not True:
                    raise ValueError('Confirme seu direito de baixar e editar este vídeo.')
                item = busca['resultados'][indice]
                canal = data.get('canal')
                if canal not in (('games',) if busca['nicho'] == 'games' else ('ia', 'tecnologia')):
                    raise ValueError('Canal de destino inválido.')
                chave_job = 'radar-' + uuid4().hex[:12]
                STATE.mkdir(exist_ok=True)
                refs = ROOT / 'trabalho/referencias'
                refs.mkdir(parents=True, exist_ok=True)
                brief = f"{busca['tema']} · {item['pilar']} · {item['titulo']}"[:20000]
                brief_path = refs / (chave_job + '.txt')
                brief_path.write_text(brief, encoding='utf-8')
                record = STATE / (chave_job + '.json')
                record.write_text(json.dumps(dict(video=chave_job, youtube=item['link'],
                    source_title=item['titulo'], source_channel=item['canal'],
                    channel=canal, status='Na fila', cuts=[], brief=brief,
                    serie=True, autorizado=True), ensure_ascii=False, indent=2), encoding='utf-8')
                JOBS.submit(importar_e_analisar, record, item['link'], brief_path,
                            canal, 5, True, True)
                self.send_json({'status': 'Na fila', 'id': chave_job})
            elif self.path == '/api/analyze':
                channel, quantity = data.get('channel'), int(data.get('quantity', 3))
                serie = data.get('serie') is True
                if data.get('youtube'):
                    if data.get('autorizado') is not True:
                        raise ValueError('Confirme a autorização para baixar e editar.')
                    if channel not in CANAIS or not 1 <= quantity <= 10:
                        raise ValueError('Canal ou quantidade inválida.')
                    link = normalizar(data['youtube'])
                    chave = 'youtube-' + uuid4().hex[:12]
                    STATE.mkdir(exist_ok=True)
                    refs = ROOT / 'trabalho/referencias'
                    refs.mkdir(parents=True, exist_ok=True)
                    brief_path = refs / f'{chave}.txt'
                    brief = str(data.get('brief', '')).strip()[:20000]
                    brief_path.write_text(brief, encoding='utf-8')
                    record = STATE / f'{chave}.json'
                    record.write_text(json.dumps(dict(video=chave, youtube=link, channel=channel,
                        status='Na fila', cuts=[], brief=brief, serie=serie, reference=data.get('reference', ''))))
                    JOBS.submit(importar_e_analisar, record, link, brief_path, channel, quantity, False, serie)
                    self.send_json({'status': 'Na fila', 'id': chave})
                    return
                rel = Path(data['video'])
                video = (ROOT / rel).resolve(strict=True)
                if channel not in CANAIS or not video.is_relative_to(ROOT / 'entrada') or not video.is_file():
                    raise ValueError('Vídeo ou canal inválido.')
                if not 1 <= quantity <= 10:
                    raise ValueError('A quantidade deve estar entre 1 e 10.')
                brief = str(data.get('brief', '')).strip()[:20000]
                refs = ROOT / 'trabalho' / 'referencias'
                refs.mkdir(parents=True, exist_ok=True)
                brief_path = refs / f'{video.stem}.txt'
                brief_path.write_text(brief, encoding='utf-8')
                STATE.mkdir(exist_ok=True)
                record = STATE / f'{video.stem}.json'
                with LOCK:
                    if record.exists() and json.loads(record.read_text()).get('status') in ('Na fila', 'Analisando'):
                        raise ValueError('Este vídeo já está sendo analisado.')
                    record.write_text(json.dumps({'video': str(rel), 'reference': data.get('reference', ''), 'channel': channel,
                        'brief': brief, 'status': 'Na fila', 'cuts': [], 'serie': serie}, ensure_ascii=False, indent=2))
                JOBS.submit(run_analysis, record, video, brief_path, channel, quantity, serie=serie)
                self.send_json({'status': 'Na fila'})
            elif self.path == '/api/approve':
                video = str(data['video'])
                record = STATE / (Path(video).stem + '.json')
                redes = data['redes']
                if not isinstance(redes, list) or not all(isinstance(r, str) for r in redes):
                    raise ValueError('Plataformas inválidas.')
                with LOCK:
                    job = json.loads(record.read_text(encoding='utf-8'))
                    corte = data['corte']
                    if job['video'] != video or corte not in job.get('arquivos', []):
                        raise ValueError('Corte indisponível para aprovação.')
                    entregas = job.get('entregas', {})
                    entregas[corte] = {**entregas.get(corte, {}), **entregar_games(corte, redes, job['channel'])}
                    update(record, entregas=entregas)
                self.send_json({'entregas': entregas[corte]})
            elif self.path == '/api/render':
                channel, slug = data.get('channel'), data.get('slug', '')
                if channel not in CANAIS or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', slug):
                    raise ValueError('Canal ou nome do corte inválido.')
                rel = Path(data['video'])
                plan = ROOT / 'trabalho' / channel / f'{Path(rel).stem}.json'
                cmd = [sys.executable, str(ROOT / 'cortes.py'), 'renderizar', str(plan),
                    '--corte', str(int(data['corte'])), '--rede', 'youtube', '--previa',
                    '--slug', slug, '--creditos', str(data.get('credits', ''))[:500]]
                result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
                if result.returncode:
                    raise ValueError(result.stderr[-1500:] or 'Falha ao renderizar prévia.')
                rendered = Path(result.stdout.strip()).resolve()
                if not rendered.is_relative_to(ROOT / 'trabalho/previas'):
                    raise ValueError('O renderizador retornou um caminho inesperado.')
                self.send_json({'path': str(rendered.relative_to(ROOT)),
                                'video': str((rendered / 'video.mp4').relative_to(ROOT))})
            else:
                self.send_json({'error': 'Não encontrado'}, 404)
        except (ValueError, KeyError, OSError, json.JSONDecodeError) as error:
            self.send_json({'error': str(error)}, 400)

    def log_message(self, fmt, *args):
        print('%s - %s' % (self.address_string(), fmt % args))


if __name__ == '__main__':
    (ROOT / 'logs').mkdir(exist_ok=True)
    logging.basicConfig(filename=ROOT / 'logs/studio.log', level=logging.INFO)
    print('CortesIA Studio local em http://127.0.0.1:8765')
    ThreadingHTTPServer(('127.0.0.1', 8765), Handler).serve_forever()

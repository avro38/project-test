"""Local preview and staged IBKR PDF import. Bind loopback only; no third-party uploads."""
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
from threading import Lock
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import unquote,urlsplit,parse_qs
import os,json,re,hashlib,secrets,shutil,subprocess,sys,time
from datetime import datetime
SITE=Path(__file__).resolve().parents[1]
SOURCE=SITE.parent
STAGED={}
PERSONAL_LOCK=Lock()
PERSONAL_FILE=Path(os.environ.get('PM_PERSONAL_FILE',str(SITE/'.personal/state.json')))
FOLDERS={'U22210104':'01_Портфель_0104','U23483251':'02_Портфель_3251'}
class Handler(SimpleHTTPRequestHandler):
 def __init__(self,*args,**kwargs):super().__init__(*args,directory=str(SITE),**kwargs)
 def json(self,status,obj):
  body=json.dumps(obj,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(body)
 def do_GET(self):
  parts=urlsplit(self.path)
  if '.personal' in unquote(parts.path).replace('\\','/').split('/'):
   self.send_error(403);return
  if parts.path=='/api/personal':
   if self.headers.get('Host') not in ['127.0.0.1:8765','localhost:8765']:
    self.json(403,{'error':'Invalid host'});return
   try:self.json(200,json.loads(PERSONAL_FILE.read_text(encoding='utf-8')) if PERSONAL_FILE.exists() else {})
   except Exception:self.json(500,{'error':'Не удалось прочитать сохранения'})
   return
  if parts.path=='/api/quotes':
   if self.headers.get('Host') not in ['127.0.0.1:8765','localhost:8765']:
    self.json(403,{'error':'Invalid host'});return
   symbols=parse_qs(parts.query).get('symbols',[''])[0].split(',')
   if len(symbols)>100 or any(not re.fullmatch(r'[A-Z][A-Z0-9.\-]{0,11}',s) for s in symbols):
    self.json(400,{'error':'Invalid symbols'});return
   from market_quotes import get_quotes
   self.json(200,get_quotes(symbols));return
  super().do_GET()
 def do_POST(self):
  try:
   if self.headers.get('Host') not in ['127.0.0.1:8765','localhost:8765']:raise ValueError('Invalid host')
   origin=self.headers.get('Origin')
   if origin and origin not in ['http://127.0.0.1:8765','http://localhost:8765']:raise ValueError('Invalid origin')
   length=int(self.headers.get('Content-Length','0'))
   if not 0<length<=30*1024*1024:raise ValueError('Максимум 30 МБ')
   body=self.rfile.read(length)
   if self.path=='/api/personal':
    if length>2*1024*1024:raise ValueError('Слишком большое сохранение')
    obj=json.loads(body);key=obj.get('key');value=obj.get('value');stamp=obj.get('updatedAt')
    if key not in ['plan','watchlist'] or not isinstance(value,dict) or not isinstance(stamp,(int,float)) or stamp<=0:raise ValueError('Неверное сохранение')
    if value.get('version')!=2:raise ValueError('Неверная версия')
    if key=='plan' and (not isinstance(value.get('portfolios'),list) or len(value['portfolios'])!=2):raise ValueError('Неверный план')
    if key=='watchlist' and not isinstance(value.get('rows'),list):raise ValueError('Неверный список')
    with PERSONAL_LOCK:
     previous=json.loads(PERSONAL_FILE.read_text(encoding='utf-8')) if PERSONAL_FILE.exists() else {}
     record={'value':value,'updatedAt':stamp}
     if previous.get(key,{}).get('updatedAt',0)>stamp:
      self.json(200,previous[key]);return
     previous[key]=record
     PERSONAL_FILE.parent.mkdir(parents=True,exist_ok=True)
     temp=PERSONAL_FILE.with_suffix('.tmp')
     temp.write_text(json.dumps(previous,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
     temp.replace(PERSONAL_FILE)
     self.json(200,record);return
   if self.path=='/api/preview':
    name=unquote(self.headers.get('X-Filename',''))
    match=re.fullmatch(r'(U22210104|U23483251)_(\d{8})_(\d{8})\.pdf',name,re.I)
    if not match or not body.startswith(b'%PDF'):raise ValueError('Нужен PDF IBKR с именем U22210104_YYYYMMDD_YYYYMMDD.pdf или U23483251_YYYYMMDD_YYYYMMDD.pdf')
    folder=FOLDERS[match[1].upper()];destination=SOURCE/folder/'Отчёты'/name
    digest=hashlib.sha256(body).hexdigest()
    if any(hashlib.sha256(p.read_bytes()).hexdigest()==digest for p in (SOURCE/folder/'Отчёты').glob('*.pdf')):raise ValueError('Этот отчёт уже загружен: одинаковый SHA-256')
    if destination.exists():raise ValueError('Файл с таким именем уже существует и отличается. Проверьте источник.')
    from pypdf import PdfReader
    import io
    text=PdfReader(io.BytesIO(body)).pages[0].extract_text()
    if match[1].upper() not in text:raise ValueError('Счёт внутри PDF не совпадает с именем файла')
    period=re.search(r'([A-Za-z]+ \d{1,2}, \d{4}) - ([A-Za-z]+ \d{1,2}, \d{4})',text)
    if not period or [datetime.strptime(period[i],'%B %d, %Y').strftime('%Y%m%d') for i in [1,2]]!=[match[2],match[3]]:raise ValueError('Период внутри PDF не совпадает с именем файла')
    with TemporaryDirectory(prefix='portfolio-import-') as temp:
     stage=Path(temp)
     for f in FOLDERS.values():shutil.copytree(SOURCE/f/'Отчёты',stage/f/'Отчёты')
     shutil.copytree(SOURCE/'04_Портфель_Iris',stage/'04_Портфель_Iris')
     (stage/folder/'Отчёты'/name).write_bytes(body)
     out=stage/'output';(out/'data').mkdir(parents=True)
     result=subprocess.run([sys.executable,'-X','utf8',str(SITE/'tools/extract_reports.py')],env={**os.environ,'PM_SOURCE_ROOT':str(stage),'PM_OUTPUT_DIR':str(out)},capture_output=True,text=True,encoding='utf8',timeout=90)
     if result.returncode:raise ValueError('PDF не прошёл сверку позиций, денежных потоков или выплат. Файлы сайта не изменены.')
     snapshot=json.loads((out/'data/portfolio-data.json').read_text(encoding='utf8'))
     for p in snapshot['portfolios']:
      if p['id']!='iris' and abs(sum(x['value'] for x in p['positions'])-p['stockValue'])>.05:raise ValueError('Не сходятся позиции')
     token=secrets.token_urlsafe(24)
     # Keep at most five pending previews, expire in ten minutes.
     for k,v in list(STAGED.items()):
      if time.time()-v['time']>600:STAGED.pop(k)
     if len(STAGED)>=5:STAGED.pop(next(iter(STAGED)))
     STAGED[token]={'time':time.time(),'body':body,'destination':destination,'data':snapshot,'before':hashlib.sha256((SITE/'data/portfolio-data.json').read_bytes()).hexdigest()}
     self.json(200,{'token':token,'data':snapshot});return
   if self.path=='/api/apply':
    token=json.loads(body).get('token');item=STAGED.pop(token,None)
    if not item or time.time()-item['time']>600:raise ValueError('Предпросмотр истёк. Выберите файл заново.')
    if item['destination'].exists():raise ValueError('Отчёт уже сохранён. Проверьте список источников.')
    if hashlib.sha256((SITE/'data/portfolio-data.json').read_bytes()).hexdigest()!=item['before']:raise ValueError('Данные изменились после предпросмотра. Повторите импорт.')
    backup=SITE/'backups'/time.strftime('%Y%m%d-%H%M%S');backup.mkdir(parents=True,exist_ok=True)
    for name in ['portfolio-data.json','portfolio-data.js']:shutil.copy2(SITE/'data'/name,backup/name)
    item['destination'].write_bytes(item['body'])
    snapshot=item['data']
    (SITE/'data/portfolio-data.json').write_text(json.dumps(snapshot,ensure_ascii=False,indent=2),encoding='utf8')
    (SITE/'data/portfolio-data.js').write_text('window.PORTFOLIO_DATA = '+json.dumps(snapshot,ensure_ascii=False)+';\n',encoding='utf8')
    self.json(200,{'ok':True});return
   self.json(404,{'error':'Неизвестный адрес'})
  except Exception as ex:self.json(400,{'error':str(ex)})
 def list_directory(self,path):self.send_error(403,'Directory listing disabled')
class Server(ThreadingHTTPServer):
 allow_reuse_address=False
 request_queue_size=64
 daemon_threads=True
if __name__=='__main__':
 print('Portfolio Manager: http://127.0.0.1:8765 — Ctrl+C to stop',flush=True)
 Server(('127.0.0.1',8765),Handler).serve_forever()

"""Exercise PDF preview/apply on isolated copies; original reports are never modified."""
from pathlib import Path
from tempfile import TemporaryDirectory
from http.server import HTTPServer
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from urllib.parse import quote
import importlib.util,json,threading,shutil,hashlib
SITE=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('portfolio_server',SITE/'tools/serve.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
with TemporaryDirectory(prefix='portfolio-import-test-') as temp:
 root=Path(temp);site=root/'00_Portfolio Manager';(site/'data').mkdir(parents=True);(site/'tools').mkdir()
 for f in module.FOLDERS.values():shutil.copytree(SITE.parent/f/'Отчёты',root/f/'Отчёты')
 shutil.copytree(SITE.parent/'04_Портфель_Iris',root/'04_Портфель_Iris')
 for name in ['portfolio-data.json','portfolio-data.js']:shutil.copy2(SITE/'data'/name,site/'data'/name)
 shutil.copy2(SITE/'tools/extract_reports.py',site/'tools/extract_reports.py')
 name='U22210104_20260101_20261016.pdf';path=root/'01_Портфель_0104'/'Отчёты'/name;pdf=path.read_bytes();path.unlink()
 module.SITE=site;module.SOURCE=root
 server=HTTPServer(('127.0.0.1',0),module.Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
 def post(endpoint,body,filename=None):
  headers={'Host':'127.0.0.1:8765','Origin':'http://127.0.0.1:8765','Content-Type':'application/pdf' if filename else 'application/json'}
  if filename:headers['X-Filename']=quote(filename)
  request=Request('http://127.0.0.1:'+str(server.server_port)+endpoint,data=body,headers=headers,method='POST')
  try:
   with urlopen(request,timeout=120) as response:return response.status,json.load(response)
  except HTTPError as err:return err.code,json.load(err)
 try:
  before=(site/'data/portfolio-data.json').read_bytes()
  status,preview=post('/api/preview',pdf,name);assert status==200,preview
  assert (site/'data/portfolio-data.json').read_bytes()==before and not path.exists()
  assert next(p for p in preview['data']['portfolios'] if p['id']=='0104')['nav']==29561.93
  status,response=post('/api/apply',json.dumps({'token':preview['token']}).encode());assert status==200,response
  assert hashlib.sha256(path.read_bytes()).digest()==hashlib.sha256(pdf).digest()
  assert list((site/'backups').glob('*/portfolio-data.json'))
  status,response=post('/api/preview',pdf,name);assert status==400 and 'SHA-256' in response['error']
  status,response=post('/api/apply',json.dumps({'token':preview['token']}).encode());assert status==400
  status,response=post('/api/preview',b'%PDFinvalid','U999_20260101_20261016.pdf');assert status==400
  print('PDF preview, no-write staging, apply, backup, duplicate hash, token replay and invalid file: PASS')
 finally:server.shutdown();server.server_close()

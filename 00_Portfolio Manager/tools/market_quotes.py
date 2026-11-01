"""Fetch public Yahoo Finance quotes; preserve source timestamps and never substitute report prices."""
import json,time,re
from pathlib import Path
from urllib.request import Request,urlopen
from concurrent.futures import ThreadPoolExecutor
SITE=Path(__file__).resolve().parents[1]
CACHE={}
def fetch_quote(symbol):
 if not re.fullmatch(r'[A-Z][A-Z0-9.\-]{0,11}',symbol):raise ValueError('Invalid ticker')
 cached=CACHE.get(symbol)
 if cached and time.time()-cached['fetchedAt']<60:return cached
 url='https://query1.finance.yahoo.com/v8/finance/chart/'+symbol+'?interval=1d&range=1d'
 with urlopen(Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=12) as response:
  meta=json.load(response)['chart']['result'][0]['meta']
 price=meta.get('regularMarketPrice');stamp=meta.get('regularMarketTime')
 if not isinstance(price,(int,float)) or price<=0 or not stamp or meta.get('currency')!='USD':raise ValueError('No USD quote')
 result={'symbol':symbol,'price':price,'time':stamp,'fetchedAt':time.time(),'currency':'USD','source':'Yahoo Finance','url':'https://finance.yahoo.com/quote/'+symbol+'/'}
 CACHE[symbol]=result
 return result
def get_quotes(symbols):
 def one(s):
  try:return s,fetch_quote(s)
  except Exception as exc:return s,{'error':'Котировка недоступна'}
 with ThreadPoolExecutor(max_workers=8) as pool:result=dict(pool.map(one,sorted(set(symbols))))
 return {'fetchedAt':time.time(),'quotes':result}
if __name__=='__main__':
 data=json.loads((SITE/'data/portfolio-data.json').read_text(encoding='utf-8-sig'))
 symbols={x['symbol'] for p in data['portfolios'] for x in p['positions']}|{'VTI','QQQM'}
 seed=(SITE/'data/watchlist-seed.js').read_text(encoding='utf-8').split('=',1)[1].strip().rstrip(';')
 symbols|={r['symbol'] for r in json.loads(seed)}
 out=get_quotes(symbols)
 (SITE/'data/market-quotes.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
 (SITE/'data/market-quotes.js').write_text('window.MARKET_QUOTES = '+json.dumps(out,ensure_ascii=False)+';\n',encoding='utf-8')
 print('Quotes:',sum('price' in q for q in out['quotes'].values()),'/',len(symbols))

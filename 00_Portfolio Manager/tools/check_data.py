from pathlib import Path
from html.parser import HTMLParser
import json,re
ROOT=Path(__file__).resolve().parents[1]
d=json.loads((ROOT/'data/portfolio-data.json').read_text(encoding='utf-8-sig'))
js=(ROOT/'data/portfolio-data.js').read_text(encoding='utf-8-sig')
assert json.loads(js.removeprefix('window.PORTFOLIO_DATA = ').rstrip().removesuffix(';'))==d
assert len(d['portfolios'])==4
for p in d['portfolios']:
    assert p['nav']>0 and p['cash']>=0
    assert len({x['symbol'] for x in p['positions']})==len(p['positions'])
    assert all(x['quantity']>0 and x['value']>=0 for x in p['positions'])
    if p['sourceType'] in ['pdf','combined']:
        assert abs(sum(x['value'] for x in p['positions'])-p['stockValue'])<.02
        assert abs(p['stockValue']+p['cash']-p['nav'])<.02
        assert abs(sum(x['gross'] for x in p['dividends'])-p['dividendGross'])<.02
        assert abs(sum(x['amount'] for x in p['taxes'])+p['tax'])<.02
        all_div=p['dividends']+p.get('dividendAdjustments',[])
        assert abs(sum(x['net'] for x in all_div)-(p['dividendGross']-p['tax']-sum(x['fee'] for x in p['dividends'])))<.02
        stock_ops=[x for x in p['transactions'] if x['source']=='Trades']
        assert abs(sum(x['commission'] for x in p['transactions'])-p['commissions'])<.03
        assert all(x['kind']=='buy' and x['amount']<0 or x['kind']=='sell' and x['amount']>0 for x in stock_ops)
        assert len({x['id'] for x in p['transactions']})==len(p['transactions'])
        deposits=[x for x in p['transactions'] if x['kind']=='deposit']
        assert all(x['currency']=='ILS' for x in deposits)
    else:
        assert p['twr'] is None and p['dividendGross'] is None and not p['transactions']
        assert abs(p['stockValue']-sum(x['value'] for x in p['positions'])-2.75)<.02
    assert abs(p['usdCash']-sum(x['quantity'] for x in p['currencies'] if x['currency']=='USD'))<.01
    print(p['id'],p['nav'],len(p['positions']),'positions — OK')
by_id={p['id']:p for p in d['portfolios']}
a,b,mine=(by_id[k] for k in ['0104','3251','mine'])
assert a['periodStart']=='2025-10-15'
assert b['periodStart']=='2026-01-02'
assert any(t['date'].startswith('2025-') for t in a['transactions'])
assert any(x['date'].startswith('2025-') for x in a['history'])
assert abs(a['dividendGross']-112.97)<.01
assert abs(a['checks']['netDividendSum']-84.82)<.01
assert abs(a['usdCash']-89.43)<.01 and abs(b['usdCash']-66.95)<.01
assert abs(mine['usdCash']-156.38)<.01
assert abs(mine['nav']-a['nav']-b['nav'])<.01
assert mine['twr'] is None
assert len(mine['transactions'])==len(a['transactions'])+len(b['transactions'])
assert {t['account'] for t in mine['transactions']}=={'0104','3251'}
for row in mine['positions']:
    source=[r for account in [a,b] for r in account['positions'] if r['symbol']==row['symbol']]
    assert abs(row['quantity']-sum(r['quantity'] for r in source))<.00001
    assert abs(row['value']-sum(r['value'] for r in source))<.01
    assert abs(row['average']-sum(r['cost'] for r in source)/sum(r['quantity'] for r in source))<.00001
assert len({r['symbol'] for r in mine['positions']})==len(mine['positions'])
print('Full period, USD-only free cash and both-account aggregation — OK')
class Links(HTMLParser):
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        for k in ['href','src']:
            v=attrs.get(k,'')
            if v and not v.startswith(('#','http','data:')):
                target=v.split('?')[0]
                assert (ROOT/target).exists(),target
for f,page in [('index.html','overview'),('positions.html','positions'),('dividends.html','dividends'),('transactions.html','transactions')]:
    text=(ROOT/f).read_text(encoding='utf-8-sig'); assert f'data-page="{page}"' in text
    Links().feed(text)
for resource in re.findall(r'url\(([^)]+)\)',(ROOT/'assets/styles.css').read_text(encoding='utf-8-sig')):
    assert (ROOT/'assets'/resource).exists(),resource
assert (ROOT/'.nojekyll').exists()
print('Data, financial reconciliations, JS/JSON parity, four pages and all local assets — OK')

for name in ['ticker','plan','performance','watchlist','imports']:
    html=(ROOT/(name+'.html')).read_text(encoding='utf8')
    assert 'assets/features.js' in html and 'assets/storage.js' in html
    assert 'data-page="'+name+'"' in html
symbols={x['symbol'] for p in d['portfolios'] for x in p['positions']+p['transactions']+p['dividends'] if x['symbol'] not in ['USD','ILS','USD.ILS','ILS.USD']}
for symbol in symbols:
    logo=ROOT/'assets/logos'/(symbol+'.png')
    assert logo.exists() and logo.read_bytes().startswith(b'\x89PNG'),symbol
print('Nine pages and all '+str(len(symbols))+' stock/ETF logos — OK')

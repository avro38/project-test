from pathlib import Path
from pypdf import PdfReader
import re,json,hashlib,os
from datetime import date as CalendarDate,timedelta
ROOT=Path(os.environ.get('PM_SOURCE_ROOT',Path(__file__).resolve().parents[2]))
OUT=Path(os.environ.get('PM_OUTPUT_DIR',ROOT/'00_Portfolio Manager'))
N=r'-?[\d,]+(?:\.\d+)?'
def num(s): return float(s.replace(',',''))
def get_sections(pages):
    headings=['Account Information','Net Asset Value','Mark-to-Market Performance Summary','Realized & Unrealized Performance Summary','Month & Year to Date Performance Summary','Cash Report','Open Positions','Forex Balances','Net Stock Position Summary','Trades','Withholding Tax','Deposits & Withdrawals','Interest Accruals','Dividends','Fees','Interest','Change in Dividend Accruals','Stock Yield Enhancement Program Securities Lent Activity','Stock Yield Enhancement Program Securities Lent Interest Details','Financial Instrument Information','Codes','Notes/Legal Notes']
    result={}; current=None
    for index,page in enumerate(pages,1):
        for line in page.extract_text().splitlines():
            line=line.strip()
            if line in headings: current=line; continue
            if line.startswith(('Activity Statement -','Generated:')): continue
            if current: result.setdefault(current,[]).append((index,line))
    return result
NAMES={'AAPL':'Apple','AVGO':'Broadcom','BABA':'Alibaba','BE':'Bloom Energy','CAT':'Caterpillar','CVX':'Chevron','GOOGL':'Alphabet','HNST':'The Honest Company','MELI':'MercadoLibre','META':'Meta Platforms','NBIS':'Nebius','NEE':'NextEra Energy','NET':'Cloudflare','NOW':'ServiceNow','NVDA':'NVIDIA','NVO':'Novo Nordisk','O':'Realty Income','PL':'Planet Labs','RKLB':'Rocket Lab','SCHD':'Schwab US Dividend Equity ETF','UEC':'Uranium Energy','V':'Visa','VOO':'Vanguard S&P 500 ETF','ADBE':'Adobe','AMD':'Advanced Micro Devices','AMZN':'Amazon','ASTS':'AST SpaceMobile','CELH':'Celsius Holdings','CGTX':'Cognition Therapeutics','CRM':'Salesforce','HOOD':'Robinhood','IONQ':'IonQ','IREN':'IREN','MSFT':'Microsoft','NFLX':'Netflix','ONDS':'Ondas','OSCR':'Oscar Health','PLTK':'Playtika','PLTR':'Palantir','SKHY':'SK Hynix ADR','SOFI':'SoFi','SOXX':'iShares Semiconductor ETF','USAR':'USA Rare Earth','BKSY':'BlackSky'}
def parse(path,id,start):
    r=PdfReader(path); sec=get_sections(r.pages); first=r.pages[0].extract_text()
    def val(label,default=None):
        m=re.search(r'^\s*'+re.escape(label)+r'\s+('+N+r')\s*$',first,re.M)
        return num(m[1]) if m else default
    positions=[]
    for page,line in sec['Open Positions']:
        m=re.fullmatch(r'([A-Z]+)\s+('+N+r')\s+1\s+('+N+r')\s+('+N+r')\s+('+N+r')\s+('+N+r')\s+('+N+r')(?:\s+.*)?',line)
        if m:
            symbol=m[1]; q,avg,cost,close,value,pnl=map(num,m.groups()[1:])
            positions.append(dict(symbol=symbol,name=NAMES.get(symbol,symbol),quantity=q,average=avg,cost=cost,price=close,value=value,pnl=pnl,type='ETF' if symbol in ['VOO','SCHD','SOXX'] else 'stock',page=page))
    totals=re.findall(r'^\s*Total\s+('+N+r')\s+('+N+r')\s+('+N+r')\s*$', '\n'.join(l for _,l in sec['Open Positions']),re.M)
    cost,stock,unrealized=map(num,totals[-1])
    currencies=[]
    for page,line in sec['Forex Balances']:
        m=re.fullmatch(r'(ILS|USD)\s+('+N+r')\s+('+N+r')\s+('+N+r')\s+('+N+r')\s+('+N+r')\s+('+N+r')',line)
        if m: currencies.append(dict(currency=m[1],quantity=num(m[2]),rate=num(m[5]),usd=num(m[6]),page=page))
    cash_m=re.search(r'^Cash\s+(?:'+N+r')\s+('+N+r')',first,re.M); cash=num(cash_m[1])
    transactions=[]
    tradeText='\n'.join(l for _,l in sec['Trades'])
    tradeText=re.sub(r'(\.\d{6,})\n(\d+)\b',r'\1\2',tradeText)
    pattern=r'\b([A-Z]+)\s+(\d{4}-\d{2}-\d{2}),\s+(\d{2}:\d{2}:\d{2})\s+'+r'\s+'.join(['('+N+')']*8)+r'\s+([A-Za-z;]+)'
    for m in re.finditer(pattern,tradeText):
        symbol,date,time=m.groups()[:3]; quantity,price,close,proceeds,commission,basis,realized,mtm=map(num,m.groups()[3:11])
        transactions.append(dict(date=date,time=time,kind='buy' if quantity>0 else 'sell',symbol=symbol,quantity=abs(quantity),price=price,amount=round(proceeds+commission,2),currency='USD',commission=abs(commission),realized=realized,source='Trades',description='Сделка с ценной бумагой'))
    # Currency trades preserve the cash leg in its original currency; USD commission is separate.
    patternFx=r'\b([A-Z]{3}\.[A-Z]{3})\s+(\d{4}-\d{2}-\d{2}),\s+(\d{2}:\d{2}:\d{2})\s+'+r'\s+'.join(['('+N+')']*5)
    for m in re.finditer(patternFx,tradeText):
        pair,date,time=m.groups()[:3]; quantity,price,proceeds,commission,mtm=map(num,m.groups()[3:])
        transactions.append(dict(date=date,time=time,kind='fx',symbol=pair,quantity=quantity,price=price,amount=proceeds,currency=pair.split('.')[1],commission=abs(commission),commissionCurrency='USD',source='Trades / Forex',description='Конвертация валюты; сумма — встречная денежная нога, комиссия в USD'))
    def events(section):
        # A dated record may wrap; retain page of its first line.
        records=[]; record=None; currency='USD'
        for page,line in sec.get(section,[]):
            if line in ['ILS','USD']: currency=line; continue
            if re.match(r'^\d{4}-\d{2}-\d{2}\s',line):
                if record: records.append(record)
                record=[page,currency,line]
            elif record and not line.startswith(('Date ','Total','Base Currency','Other Fees','Symbol ')):
                record[2]+=' '+line
        if record: records.append(record)
        result=[]
        for page,currency,text in records:
            m=re.match(r'^(\d{4}-\d{2}-\d{2})\s+(.+?)\s+('+N+r')$',text)
            if m: result.append(dict(date=m[1],description=m[2],amount=num(m[3]),currency=currency,page=page))
        return result
    dividend_events=events('Dividends'); taxes=events('Withholding Tax'); fees=events('Fees')
    dividends=[]
    for d in dividend_events:
        sm=re.match(r'([A-Z]+)\(',d['description']); symbol=sm[1] if sm else '—'
        tax=sum(t['amount'] for t in taxes if t['date']==d['date'] and t['description'].startswith(symbol+'('))
        fee=sum(t['amount'] for t in fees if t['date']==d['date'] and t['currency']=='USD' and t['description'].startswith(symbol+'('))
        dividends.append(dict(**d,symbol=symbol,gross=d['amount'],tax=round(-tax,2),fee=round(-fee,2),net=round(d['amount']+tax+fee,2)))
    adjustments=[]
    linked={(d['date'],d['symbol']) for d in dividends}
    for t in taxes:
        sm=re.match(r'([A-Z]+)\(',t['description']); symbol=sm[1] if sm else '—'
        if (t['date'],symbol) not in linked:
            adjustments.append(dict(**t,symbol=symbol,gross=0,tax=round(-t['amount'],2),fee=0,net=t['amount'],adjustment=True))
    for section,kind in [('Dividends','dividend'),('Withholding Tax','tax'),('Deposits & Withdrawals','deposit'),('Fees','fee'),('Interest','interest')]:
        for e in events(section):
            symbolMatch=re.match(r'([A-Z]+)\(',e['description'])
            transactions.append(dict(**e,kind=kind if kind!='deposit' or e['amount']>=0 else 'withdrawal',symbol=symbolMatch[1] if symbolMatch else e['currency'],commission=0,quantity=None,price=None,source=section))
    for i,t in enumerate(transactions): t['id']=id+'-'+str(i+1)
    result=dict(id=id,label=id,owner='Мой',asOf='2026-10-16',periodStart=start,periodEnd='2026-10-16',sourceType='pdf',sources=[dict(file=path.name,folder=str(path.parent.relative_to(ROOT)),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),pages=len(r.pages))],nav=val('Ending Value'),starting=val('Starting Value'),cash=cash,stockValue=stock,cost=cost,unrealized=unrealized,twr=num(re.search(r'Time Weighted Rate of Return\s+('+N+r')%',first)[1]),deposits=val('Deposits & Withdrawals',0),dividendGross=val('Dividends',0),tax=abs(val('Withholding Tax',0)),fees=abs(val('Other Fees',0)),commissions=abs(val('Commissions',0)),positions=positions,currencies=currencies,dividends=dividends,dividendAdjustments=adjustments,taxes=taxes,transactions=transactions,history=[])
    history={}
    for report in sorted(path.parent.glob('*.pdf')):
        text=PdfReader(report).pages[0].extract_text()
        ending=re.search(r'Ending Value\s+('+N+')',text)
        beginning=re.search(r'Starting Value\s+('+N+')',text)
        parts=report.stem.split('_')
        if ending and len(parts)>=3:
            ds=parts[-1]; end_date=ds[:4]+'-'+ds[4:6]+'-'+ds[6:]
            history[end_date]=dict(date=end_date,value=num(ending[1]),file=report.name)
        if beginning and len(parts)>=3:
            ds=parts[-2]; start_date=CalendarDate.fromisoformat(ds[:4]+'-'+ds[4:6]+'-'+ds[6:])-timedelta(days=1)
            history[start_date.isoformat()]=dict(date=start_date.isoformat(),value=num(beginning[1]),file=report.name,starting=True)
    result['history']=[history[d] for d in sorted(history)]
    # Cent rounding in PDF lines can differ from the statement totals.
    result['checks']=dict(positionValueSum=round(sum(p['value'] for p in positions),2),positionPnlSum=round(sum(p['pnl'] for p in positions),2),dividendSum=round(sum(d['gross'] for d in dividends),2),netDividendSum=round(sum(d['net'] for d in dividends+adjustments),2),taxSum=round(-sum(t['amount'] for t in taxes),2),tradeCommission=round(sum(t['commission'] for t in transactions),2))
    assert abs(result['checks']['positionValueSum']-stock)<.05
    assert abs(result['checks']['dividendSum']-result['dividendGross'])<.02
    assert abs(result['checks']['taxSum']-result['tax'])<.02
    assert abs(result['checks']['netDividendSum']-(result['dividendGross']-result['tax']-sum(d['fee'] for d in dividends)))<.02
    assert abs(result['checks']['tradeCommission']-result['commissions'])<.03
    assert abs(stock+cash-result['nav'])<.03
    end=path.stem.split('_')[-1]
    result['asOf']=result['periodEnd']=end[:4]+'-'+end[4:6]+'-'+end[6:]
    return result
if __name__=='__main__':
    def latest(folder):
        return max((ROOT/folder/'Отчёты').glob('*.pdf'),key=lambda x:x.stem.split('_')[-1])
    pa=latest('01_Портфель_0104'); pb=latest('02_Портфель_3251')
    def start_date(path):
        d=path.stem.split('_')[-2]; return d[:4]+'-'+d[4:6]+'-'+d[6:]
    a=parse(pa,'0104',start_date(pa))
    b=parse(pb,'3251',start_date(pb))
    # Retain the newest holdings, but use the broadest available history.
    def expand_history(current, folder):
        paths=list((ROOT/folder/'Отчёты').glob('*.pdf'))
        broad=min(paths,key=lambda x:(x.stem.split('_')[-2],-int(x.stem.split('_')[-1])))
        if start_date(broad)>=current['periodStart']:
            current['historyStart']=current['periodStart']
            current['twrDerived']=False
            return current
        full=parse(broad,current['id'],start_date(broad)); cutoff=full['asOf']
        tail=[dict(t) for t in current['transactions'] if t['date']>cutoff]
        new_cash=[t for t in tail if t['kind'] in ['deposit','withdrawal']]
        if any(t['currency']!='USD' for t in new_cash):
            raise ValueError('Manual FX reconciliation required for non-USD deposits after the long-period report')
        for key in ['transactions','dividends','taxes','dividendAdjustments']:
            current[key]=full.get(key,[])+[x for x in current.get(key,[]) if x['date']>cutoff]
        current['sources'].extend(dict(x,role='full-history') for x in full['sources'])
        current['starting']=full['starting'];current['deposits']=round(full['deposits']+sum(t['amount'] for t in new_cash),2)
        current['periodStart']=full['periodStart'];current['historyStart']=full['periodStart']
        current['dividendGross']=round(sum(d['gross'] for d in current['dividends']),2)
        current['tax']=round(-sum(t['amount'] for t in current['taxes']),2)
        current['commissions']=round(full['commissions']+sum(t['commission'] for t in tail),2)
        current['fees']=full['fees']
        # A one-day tail without external cash flows can be chained to broker TWR.
        if not new_cash and current['asOf']=='2026-10-16' and cutoff=='2026-10-15':
            current['twr']=((1+full['twr']/100)*current['nav']/full['nav']-1)*100
            current['twrDerived']=True
            current['twrNote']='Оценка: TWR 25,02% по 15.10.2026 × изменение NAV за 16.10 без внешних потоков. Исходная TWR округлена брокером.'
        else:
            current['twr']=None;current['twrDerived']=False
        current['notes']=['История с '+full['periodStart']+' из полного отчёта по '+cutoff+'; позиции и баланс — из свежего отчёта '+current['asOf']+'. Пересекающиеся периоды не суммируются.']
        return current
    a=expand_history(a,'01_Портфель_0104');b=expand_history(b,'02_Портфель_3251')
    for account in [a,b]:
        account['usdCash']=next((x['quantity'] for x in account['currencies'] if x['currency']=='USD'),0)
        account['periodProfit']=round(account['nav']-account['starting']-account['deposits'],2)
        for key in ['positions','transactions','dividends','taxes','dividendAdjustments']:
            for i,row in enumerate(account.get(key,[])):
                row['account']=account['id']
                if key=='transactions': row['id']=account['id']+'-'+str(i+1)
        account['checks']=dict(positionValueSum=round(sum(x['value'] for x in account['positions']),2),dividendSum=round(sum(x['gross'] for x in account['dividends']),2),taxSum=account['tax'],netDividendSum=round(sum(x['net'] for x in account['dividends']+account.get('dividendAdjustments',[])),2),tradeCommission=round(sum(x['commission'] for x in account['transactions']),2))
    # Iris: manual transcription; holdings screenshot 09:43, balance screenshot 09:44.
    rows=[('AMZN',5,250.46,253.23,1266,13.72),('AVGO',2,361.02,344.29,688.54,-33.51),('BKSY',20,43.10,17.16,343.23,-518.77),('GOOGL',8,358.38,347.14,2777,-89.80),('META',6,614.89,735.43,4413,723.20),('NBIS',2,185.32,183.96,367.82,-2.82),('PL',68,47.60,14.12,960.16,-2277),('PLTR',7,156.90,200.86,1406,308.02)]
    pos=[dict(symbol=s,name=NAMES[s],quantity=q,average=avg,cost=round(q*avg,2),price=price,value=value,pnl=pnl,type='stock',precision='screenshot') for s,q,avg,price,value,pnl in rows]
    iris=dict(id='iris',label='Iris',owner='Iris',asOf='2026-10-15',periodStart=None,periodEnd='2026-10-15',sourceType='screenshot',sources=[dict(file=p.name,folder='04_Портфель_Iris',sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted((ROOT/'04_Портфель_Iris').glob('*.jpg'))],nav=12351.36,starting=None,cash=126.86,stockValue=12224.50,cost=None,unrealized=-1872,twr=None,deposits=None,dividendGross=None,tax=None,fees=None,commissions=None,positions=pos,currencies=[dict(currency='USD',quantity=126.86,rate=1,usd=126.86)],dividends=[],taxes=[],transactions=[],history=[],notes=['Баланс взят со снимка 09:44; позиции — со снимка 09:43. Даты взяты из имён файлов, дата внутри приложения не показана.','Суммы строк и P/L округлены на скриншоте. Сумма позиций 12 221,75 USD отличается от Securities Gross Position Value 12 224,50 USD на 2,75 USD.','Нет отчёта о сделках, дивидендах и доходности за период. Средняя цена переписана со скриншота и не используется для восстановления точной себестоимости.'])
    iris['usdCash']=iris['cash'];iris['historyStart']=None;iris['periodProfit']=None
    # Both personal accounts, never Iris. Merge rows by the full stock ticker.
    combined_positions={}
    for account in [a,b]:
        for row in account['positions']:
            symbol=row['symbol']
            if symbol not in combined_positions:
                combined_positions[symbol]=dict(row,quantity=0,cost=0,value=0,pnl=0,members=[])
            dest=combined_positions[symbol]
            for key in ['quantity','cost','value','pnl']: dest[key]+=row[key]
            dest['members'].append(dict(account=account['id'],quantity=row['quantity'],value=row['value'],cost=row['cost'],pnl=row['pnl'],page=row['page']))
    for row in combined_positions.values():
        row['average']=row['cost']/row['quantity']
        for key in ['cost','value','pnl']:row[key]=round(row[key],2)
    combined=dict(id='mine',label='Мои вместе',owner='0104 + 3251',asOf=a['asOf'],periodStart=a['periodStart'],periodEnd=a['asOf'],historyStart=a['periodStart'],sourceType='combined',sources=[dict(s,account=x['id']) for x in [a,b] for s in x['sources']],positions=list(combined_positions.values()),twr=None,twrDerived=False,history=[],notes=['Объединены только счета 0104 и 3251. Iris не входит.','0104: история с 15.10.2025; 3251: доступные отчёты с 02.01.2026. Общая TWR не рассчитывается как сумма или среднее разных периодов.'])
    for key in ['nav','starting','cash','usdCash','stockValue','cost','unrealized','deposits','dividendGross','tax','fees','commissions','periodProfit']:
        combined[key]=round(a[key]+b[key],2)
    for key in ['transactions','dividends','taxes','dividendAdjustments']:
        combined[key]=[dict(r) for x in [a,b] for r in x.get(key,[])]
    combined['currencies']=[dict(currency=c,quantity=round(sum(r['quantity'] for x in [a,b] for r in x['currencies'] if r['currency']==c),2),usd=round(sum(r['usd'] for x in [a,b] for r in x['currencies'] if r['currency']==c),2)) for c in ['USD','ILS']]
    dates=set(x['date'] for x in a['history'])&set(x['date'] for x in b['history'])
    combined['history']=[dict(date=d,value=round(next(x['value'] for x in a['history'] if x['date']==d)+next(x['value'] for x in b['history'] if x['date']==d),2)) for d in sorted(dates)]
    combined['checks']=dict(positionValueSum=round(sum(x['value'] for x in combined['positions']),2),dividendSum=round(sum(x['gross'] for x in combined['dividends']),2),taxSum=combined['tax'],netDividendSum=round(sum(x['net'] for x in combined['dividends']+combined['dividendAdjustments']),2),tradeCommission=round(sum(x['commission'] for x in combined['transactions']),2))
    data=dict(version=2,generatedAt=CalendarDate.today().isoformat(),baseCurrency='USD',portfolios=[a,b,iris,combined])
    (OUT/'data/portfolio-data.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    (OUT/'data/portfolio-data.js').write_text('window.PORTFOLIO_DATA = '+json.dumps(data,ensure_ascii=False)+';\n',encoding='utf-8')
    for p in [a,b]: print(p['id'],len(p['positions']),'positions',len(p['transactions']),'operations',len(p['dividends']),'dividends',p['checks'])

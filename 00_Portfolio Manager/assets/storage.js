try { const d=JSON.parse(localStorage.getItem('pm-snapshot')); if(d&&d.baseCurrency==='USD'&&Array.isArray(d.portfolios)&&d.portfolios.length===4)window.PORTFOLIO_DATA=d; } catch {}

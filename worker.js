export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const path = url.pathname;
    const cors = { 'Access-Control-Allow-Origin': '*', 'Content-Type': 'application/json; charset=utf-8' };

    if (path === '/api/reports' || path === '/api/reports/') {
      const list = await env.REPORTS.list({ prefix: 'report:' });
      const reports = [];
      for (const key of list.keys) {
        let data = null;
        try {
          data = await env.REPORTS.get(key.name, 'json');
        } catch (_e) {
          const text = await env.REPORTS.get(key.name);
          try { data = JSON.parse(text); } catch (_e2) { data = null; }
        }
        if (data) {
          const meta = Array.isArray(data) ? (data.find(b => b.type === 'meta') || {}) : (data.meta || data);
          reports.push({
            slug: key.name.replace('report:', ''),
            date_label: meta.date_label || meta.date || '',
            data_date: meta.data_date || '',
            excerpt: meta.excerpt || meta.summary || '',
            tags: meta.tags || []
          });
        }
      }
      reports.sort((a, b) => b.slug.localeCompare(a.slug));
      return new Response(JSON.stringify(reports), { headers: cors });
    }

    if (path.startsWith('/api/reports/')) {
      const slug = path.replace('/api/reports/', '');
      let data = null;
      try {
        data = await env.REPORTS.get(`report:${slug}`, 'json');
      } catch (_e) {
        const text = await env.REPORTS.get(`report:${slug}`);
        try { data = JSON.parse(text); } catch (_e2) { data = null; }
      }
      if (!data) {
        return new Response(JSON.stringify({ error: 'Report not found' }), { status: 404, headers: cors });
      }
      return new Response(JSON.stringify(data), { headers: cors });
    }

    if (path === '/api/trigger') {
      try {
        await generateDailyReport(env);
        return new Response(JSON.stringify({ ok: true }), { headers: cors });
      } catch (e) {
        return new Response(JSON.stringify({ ok: false, error: String(e) }), { status: 500, headers: cors });
      }
    }

    return env.ASSETS.fetch(request);
  },

  async scheduled(event, env, ctx) {
    console.log('Cron triggered at', new Date().toISOString());
    try {
      await generateDailyReport(env);
      console.log('Daily report generated successfully');
    } catch (e) {
      console.error('Failed to generate daily report:', e);
    }
  }
};

async function generateDailyReport(env) {
  const now = new Date();
  const nyTime = new Date(now.toLocaleString('en-US', { timeZone: 'America/New_York' }));
  const tradeDate = nyTime.toISOString().slice(0, 10);
  const dateLabel = `${nyTime.getMonth() + 1}月${nyTime.getDate()}日`;

  // Fetch data
  const spx = await fetchYahoo('^GSPC');
  const dji = await fetchYahoo('^DJI');
  const ixic = await fetchYahoo('^IXIC');
  const vix = await fetchYahoo('^VIX');

  // Accurate summary from template (data 100% correct)
  const upDown = (spx.changePct >= 0 && dji.changePct >= 0 && ixic.changePct >= 0) ? '齊漲' :
                 (spx.changePct <= 0 && dji.changePct <= 0 && ixic.changePct <= 0) ? '齊跌' : '分化';
  const summary = `截至${dateLabel}收盤，美國三大股指${upDown}。標普500收報${spx.price.toFixed(2)}點（${formatChange(spx.changePct)}）、道瓊斯收報${dji.price.toFixed(2)}點（${formatChange(dji.changePct)}）、納斯達克收報${ixic.price.toFixed(2)}點（${formatChange(ixic.changePct)}）。VIX 恐慌指數收報${vix.price.toFixed(2)}點（${formatChange(vix.changePct)}）。`;

  // Optional AI sentiment (no numbers, purely qualitative)
  let sentiment = '';
  if (env.AI) {
    try {
      const prompt = `你是一位美股市場分析師。根據以下定性趨勢，用繁體中文寫一段約60字的市場情緒描述（不引用任何具體數字），僅描述整體氛圍與關鍵觀察。語氣專業簡潔。

趨勢：標普500${spx.changePct >= 0 ? '上漲' : '下跌'}、道瓊斯${dji.changePct >= 0 ? '上漲' : '下跌'}、納斯達克${ixic.changePct >= 0 ? '上漲' : '下跌'}、VIX${vix.changePct >= 0 ? '上升' : '下降'}。`;
      const aiRes = await env.AI.run('@cf/meta/llama-3.1-8b-instruct', { messages: [{ role: 'user', content: prompt }] });
      sentiment = (aiRes.response?.text || aiRes.response || '').trim();
    } catch (_e) { sentiment = ''; }
  }

  const blocks = [
    { type: 'meta', date: tradeDate, data_date: tradeDate, date_label: dateLabel, excerpt: summary, tags: ['自動生成'] },
    { type: 'h1', text: '一、市場概覽' },
    { type: 'body', text: summary + (sentiment ? '\n\n' + sentiment : '') },
    { type: 'h2', text: '1.1 主要指數表現' },
    { type: 'table', headers: ['指數', '收盤點位', '日漲跌幅', '數據來源'], rows: [
      ['標普500', spx.price.toFixed(2), formatChange(spx.changePct), 'Yahoo Finance'],
      ['道瓊斯', dji.price.toFixed(2), formatChange(dji.changePct), 'Yahoo Finance'],
      ['納斯達克', ixic.price.toFixed(2), formatChange(ixic.changePct), 'Yahoo Finance'],
    ], caption: `數據截至${dateLabel}收盤` },
    { type: 'h2', text: '1.2 VIX 恐慌指數' },
    { type: 'table', headers: ['指標', '收報', '日漲跌幅', '數據來源'], rows: [
      ['VIX', vix.price.toFixed(2), formatChange(vix.changePct), 'Yahoo Finance']
    ], caption: `數據截至${dateLabel}收盤` },
    { type: 'h2', text: '二、市場展望與風險提示' },
    { type: 'body', text: '本報告由自動化系統根據公開數據生成，僅供參考，不構成投資建議。市場波動受多重因素影響，建議結合基本面與技術面綜合判斷。' },
  ];

  await env.REPORTS.put(`report:${tradeDate}`, JSON.stringify(blocks));
}

async function fetchYahoo(symbol) {
  const url = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(symbol)}?interval=1d&range=5d`;
  const res = await fetch(url, {
    headers: { 'User-Agent': 'Mozilla/5.0 (compatible; Bot/1.0)' },
    cf: { cacheTtl: 300 }
  });
  if (!res.ok) throw new Error(`Yahoo API error for ${symbol}: ${res.status}`);
  const data = await res.json();
  const result = data.chart.result[0];
  const meta = result.meta;
  const closes = result.indicators.quote[0].close;
  // Find last valid close (most recent trading day)
  let lastValidIdx = closes.length - 1;
  while (lastValidIdx >= 0 && closes[lastValidIdx] === null) lastValidIdx--;
  const lastPrice = lastValidIdx >= 0 ? closes[lastValidIdx] : meta.regularMarketPrice;
  // Find previous valid close (trading day before last)
  let prevValidIdx = lastValidIdx - 1;
  while (prevValidIdx >= 0 && closes[prevValidIdx] === null) prevValidIdx--;
  const prevPrice = prevValidIdx >= 0 ? closes[prevValidIdx] : (meta.chartPreviousClose || lastPrice);
  const change = lastPrice - prevPrice;
  const changePct = prevPrice ? (change / prevPrice * 100) : 0;
  return { price: lastPrice, prev: prevPrice, change, changePct };
}

function formatChange(pct) {
  const sign = pct >= 0 ? '+' : '';
  return `${sign}${pct.toFixed(2)}%`;
}

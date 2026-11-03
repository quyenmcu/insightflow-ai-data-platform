export const fields = ['orders','delivered','labeled','late','gmv_cents','freight_cents','payments_cents'];
export const sum = rows => Object.fromEntries(fields.map(k => [k, rows.reduce((n,r) => n+r[k],0)]));
export const money = cents => new Intl.NumberFormat('en-US',{style:'currency',currency:'BRL',maximumFractionDigits:2}).format(cents/100);
export const number = value => new Intl.NumberFormat('en-US').format(value);
export const percent = value => value === null ? 'Not available' : `${(value*100).toFixed(2)}%`;
export function selectRows(snapshot, filters) {
  if (!/^\d{4}-\d{2}$/.test(filters.from) || !/^\d{4}-\d{2}$/.test(filters.to) || filters.from > filters.to) throw new Error('Choose a start month on or before the end month.');
  return snapshot.rows.filter(r => r.month >= filters.from && r.month <= filters.to && (filters.state === 'all' || r.state === filters.state));
}
export function summarize(rows) {
  const total = sum(rows);
  return {...total, lateRate:total.labeled ? total.late/total.labeled : null,
    aovCents:total.delivered ? total.gmv_cents/total.delivered : null};
}
export function group(rows, dimension) {
  const groups = new Map();
  for (const row of rows) { if (!groups.has(row[dimension])) groups.set(row[dimension],[]); groups.get(row[dimension]).push(row); }
  return [...groups].map(([key,items]) => ({key,...summarize(items)})).sort((a,b) => a.key.localeCompare(b.key));
}
export const questions = [
  ['gmv','What is our delivered GMV?'], ['delay','How many deliveries were late?'],
  ['state','Which customer state leads sales?'], ['aov','What is the average order value?'],
  ['month','Which month had the highest GMV?'], ['payments','What are delivered payment totals?']
];
const aliases = {
  gmv:['gmv','sales','delivered gmv','what is our delivered gmv','what is the gmv','how much did we sell'],
  delay:['late deliveries','delay rate','how many deliveries were late','what is the late delivery rate'],
  state:['top state','which customer state leads sales','which state has the highest gmv'],
  aov:['aov','average order value','what is the average order value'],
  month:['best month','which month had the highest gmv'],
  payments:['payments','what are delivered payment totals']
};
export function answerQuestion(question, rows) {
  const normalized = question.toLowerCase().trim().replace(/[?.!]+$/,'').replace(/\s+/g,' ');
  const key = Object.keys(aliases).find(k => aliases[k].includes(normalized));
  if (!key) return {supported:false,text:'I can answer the six metric questions shown below using the selected month range and state. Choose a suggestion, or set the filters to change the scope. I cannot explain causes, forecast sales, or run arbitrary queries.'};
  if (!rows.length) return {supported:true,text:'There are no orders in this selection. Change the month range or customer state.',formula:'No matching month/state groups.'};
  const t = summarize(rows);
  let text, formula;
  if (key === 'gmv') { text = `Delivered item GMV is ${money(t.gmv_cents)} across ${number(t.delivered)} delivered orders. Freight is excluded. This is merchandise value, not net revenue or profit.`; formula='SUM(items_value_brl) WHERE order_status = delivered'; }
  if (key === 'delay') { text = t.labeled ? `${number(t.late)} of ${number(t.labeled)} labeled delivered orders were late (${percent(t.lateRate)}). ${number(t.delivered-t.labeled)} delivered orders have no usable delay label.` : 'There are no labeled deliveries in this selection, so a delay rate cannot be calculated.'; formula='Late delivered orders / delivered orders with both actual and estimated delivery dates; compare calendar dates.'; }
  if (key === 'aov') { text = t.aovCents === null ? 'There are no delivered orders in this selection.' : `Average delivered order item value is ${money(t.aovCents)}. Freight is excluded; this is total item GMV divided by delivered orders.`; formula='SUM(delivered item GMV) / COUNT(delivered orders)'; }
  if (key === 'payments') { text=`Delivered-order payments total ${money(t.payments_cents)}; delivered freight totals ${money(t.freight_cents)}. Payments and item GMV measure different things and need not match.`; formula='SUM(payment_value_brl) WHERE order_status = delivered; payments aggregated to each order before joining.'; }
  if (key === 'state' || key === 'month') {
    const dimension = key === 'state' ? 'state' : 'month';
    const top = group(rows,dimension).filter(r=>r.delivered>0).sort((a,b)=>b.gmv_cents-a.gmv_cents || a.key.localeCompare(b.key))[0];
    text = top ? `${top.key} leads this selection with ${money(top.gmv_cents)} in delivered item GMV from ${number(top.delivered)} delivered orders. Ties use alphabetical order.` : 'There are no delivered orders to rank in this selection.';
    formula=`SUM(delivered item GMV) GROUP BY ${dimension === 'state' ? 'customer_state' : 'purchase calendar month'}; descending GMV, then group name.`;
  }
  return {supported:true,text,formula};
}
export function csvReport(rows) {
  const escape = value => `"${String(value).replace(/"/g,'""')}"`;
  const lines = [['purchase_month','customer_state',...fields]];
  for (const row of rows) lines.push([row.month,row.state,...fields.map(k=>row[k])]);
  return '\uFEFF'+lines.map(r=>r.map(escape).join(',')).join('\r\n');
}

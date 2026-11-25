import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {quote,parsePrice,schedule,localNow,filterRows,rows,validateSaved,comparisonCSV,safeURL,validDate,reviewAge,monitorSummary} from '../web/model.mjs';
const catalogue=JSON.parse(readFileSync(new URL('../web/data/catalogue.json',import.meta.url))),items=rows(catalogue);
test('decimal input becomes cents before multiplication; tax rounds once on the order',()=>{
 assert.equal(parsePrice('14.95'),1495);assert.equal(parsePrice('0.1'),10);assert.equal(parsePrice(' 15 '),1500);
 assert.deepEqual(quote(1495,2,true),{subtotal:2990,hst:419,total:3409});
 assert.deepEqual(quote(1599,2,false),{subtotal:3198,hst:0,total:3198});
 for(const bad of ['1e2','NaN','-1','1.001','10,99','10000','$10'])assert.throws(()=>parsePrice(bad));
 for(const q of [0,1.5,21,NaN])assert.throws(()=>quote(100,q,true));
});
test('market price remains unknown through sorting and totals',()=>{
 assert.deepEqual(quote(null,20,true),{subtotal:null,hst:null,total:null});
 const sorted=filterRows(items,{sort:'price'});assert.equal(sorted.at(-1).cents,null);
 assert.ok(filterRows(items,{priced:true}).every(i=>i.cents!==null));
 assert.equal(filterRows(items,{q:'Mic Mac'})[0].cents,null);
});
test('hours include previous-day overnight windows and exclude exact closing',()=>{
 const week=[[660,1500],[],null,[],[],[660,1560],[660,1560]];
 assert.equal(schedule(week,'2026-11-28','01:59').state,'listed');
 assert.equal(schedule(week,'2026-11-28','02:00').state,'outside');
 assert.equal(schedule(week,'2026-11-30','00:59').state,'listed');
 assert.equal(schedule(week,'2026-11-30','01:00').state,'outside');
 assert.equal(schedule(week,'2026-12-01','12:00').state,'unknown');
 assert.equal(schedule(null,'2026-12-01','12:00').state,'unknown');
 assert.equal(schedule(week,'2026-02-30','12:00').state,'invalid');
 assert.equal(schedule(week,'2026-12-01','24:00').state,'invalid');
});
test('Halifax local time observes winter and daylight saving offsets',()=>{
 assert.deepEqual(localNow(new Date('2026-11-25T02:30:00Z')),{date:'2026-11-24',time:'22:30'});
 assert.deepEqual(localNow(new Date('2026-07-01T03:30:00Z')),{date:'2026-07-01',time:'00:30'});
 assert.equal(validDate('2025-02-29'),false);assert.equal(validDate('2024-02-29'),true);
 assert.equal(reviewAge('2026-11-01',new Date('2026-11-25T12:00:00Z')),24);
});
test('coverage and filters expand beyond the starter collection without inference',()=>{
 const expanded=structuredClone(catalogue);expanded.restaurants.push({...expanded.restaurants[0],id:'new-place',name:'New Quote Shop',area:'New Area'});expanded.items.push({...expanded.items[0],id:'new-item',restaurant_id:'new-place',type:'strips',cents:1200,portion:'Small, weight unknown'});
 const all=rows(expanded);assert.equal(all.length,items.length+1);assert.equal(filterRows(all,{area:'New Area',type:'strips'})[0].portion,'Small, weight unknown');
 assert.ok(filterRows(items,{type:'whole'}).every(i=>i.type==='whole'));
 assert.equal(filterRows(items,{favorites:true},new Set(['uncle-bucks'])).length,3);
 assert.ok(items.every(i=>i.channel));
});
test('saved observations retain their own prices, dates and unknown values',()=>{
 const original={schema:'clamcounter.comparison.v1',saved_at:'2026-11-25T02:00:00Z',qty:2,tax:true,items:[{...items[0],cents:1234,reviewed_at:'2026-01-01'},items.find(i=>i.cents===null)]};
 const saved=validateSaved(original);assert.equal(saved.items[0].cents,1234);assert.equal(saved.items[0].reviewed_at,'2026-01-01');assert.equal(saved.items[1].cents,null);assert.equal(saved.items[0].week,null);assert.equal(saved.items[0].origin,'saved');
 assert.throws(()=>validateSaved({...original,items:Array(9).fill(items[0])}));
 assert.throws(()=>validateSaved({...original,qty:0}));
 assert.throws(()=>validateSaved({...original,items:[items[0],items[0]]}));
 assert.throws(()=>validateSaved({...original,items:[{...items[0],cents:'12.34'}]}));
 assert.throws(()=>validateSaved({...original,items:[{...items[0],reviewed_at:'2026-02-30'}]}));
 assert.equal(validateSaved({...original,items:[{...items[0],menu_url:'javascript:alert(1)'}]}).items[0].menu_url,'');
});
test('CSV preserves exact totals, escapes quotes and blocks spreadsheet formulas after spaces',()=>{
 const row={...items[0],restaurant:'  =SUM(1,2)',portion:'A "small" dish',cents:1495};
 const csv=comparisonCSV([row],2,true);assert.ok(csv.includes('"\'  =SUM(1,2)"'));assert.ok(csv.includes('A ""small"" dish'));assert.ok(csv.includes('"29.90","4.19","34.09"'));
 assert.ok(comparisonCSV([{...row,cents:null}],1,false).includes('"1","","","",""'));
 assert.equal(safeURL('https://user:pass@example.com/'),'');assert.equal(safeURL('http://example.com/'),'');
});
test('source failures and changes cannot be counted as a clean monitor',()=>{
 assert.deepEqual(monitorSummary({sources:[{status:'ok'},{status:'needs_review'},{status:'error'}]}),{ok:2,changed:1,failed:1});
 assert.deepEqual(monitorSummary({sources:[{state:'unchanged'}]}),{ok:0,changed:0,failed:1});
 assert.throws(()=>monitorSummary({sources:[]}));
});

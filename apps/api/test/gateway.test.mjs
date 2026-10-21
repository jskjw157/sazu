import { test } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { existsSync } from 'node:fs';

const CLIENT = 'b'.repeat(64), INTERNAL = 'a'.repeat(64);
const VERSION = 'sazu.foundation.v1';
const BODY = { kind: 'gregorian', year: 2024, month: 2, day: 10 };
const PATH = '/v1/research/calendar';
const AUTH = { authorization: `Bearer ${CLIENT}`, 'content-type': 'application/json' };

async function modules() {
  assert.ok(existsSync(new URL('../dist/app.js', import.meta.url)), 'Express gateway is not implemented');
  return { ...(await import('../dist/app.js')), ...(await import('../dist/config.js')) };
}
async function serve(t, handler) {
  const server = http.createServer(handler);
  await new Promise(r => server.listen(0, '127.0.0.1', r));
  t.after(() => new Promise(r => { server.closeAllConnections(); server.close(r); }));
  return `http://127.0.0.1:${server.address().port}`;
}
function calendarResult(body=BODY) {
  return { request: {...body, leap: body.leap ?? null},
    candidates: [{solar:'2024-02-10',lunar_year:2024,lunar_month:1,lunar_day:1,is_leap:false}],
    library_version:'fixture', library_sha256:'c'.repeat(64),
    evidence_level:'library_regression_not_official_verification' };
}
function reply(req, res, extra={}) {
  res.writeHead(200, {'content-type':'application/json','x-sazu-contract':VERSION});
  res.end(JSON.stringify({ok:true,contract_version:VERSION,production_authorized:false,
    request_id:req.headers['x-request-id'],result:calendarResult(),...extra}));
}
async function fixture(t, handler=(req,res)=>reply(req,res), options={}) {
  const {createApp,loadConfig} = await modules();
  const upstream = await serve(t,handler);
  const config = loadConfig({SAZU_MODE:'research',RESEARCH_API_TOKEN:CLIENT,CALCULATOR_TOKEN:INTERNAL,
    PYTHON_BASE_URL:upstream,DATABASE_URL:'postgresql://sazu:fixture@localhost/sazu',
    PYTHON_TIMEOUT_MS:'200',...options.env});
  const app = createApp(config,{checkDatabase:async()=>{},...options.dependencies});
  return {url:await serve(t,app),app,config};
}
async function post(url, body=BODY, headers=AUTH) {
  return fetch(url+PATH,{method:'POST',headers,body:typeof body==='string'?body:JSON.stringify(body)});
}

test('gateway preserves result, strips client credentials and uses private protocol', async t=>{
  let seen;
  const {url}=await fixture(t,async(req,res)=>{
    let raw='';for await(const c of req) raw+=c;
    seen={headers:req.headers,raw,path:req.url};reply(req,res);
  });
  const r=await post(url,BODY,{...AUTH,cookie:'private=do-not-forward','x-request-id':'user-private'});
  assert.equal(r.status,200);const b=await r.json();assert.deepEqual(b.result,calendarResult());
  assert.equal(b.production_authorized,false);assert.equal(b.contract_version,VERSION);
  assert.match(b.request_id,/^[a-f0-9-]{36}$/);assert.notEqual(b.request_id,'user-private');
  assert.equal(r.headers.get('x-powered-by'),null);assert.equal(r.headers.get('cache-control'),'no-store');
  assert.equal(seen.headers.authorization,`Bearer ${INTERNAL}`);assert.equal(seen.headers.cookie,undefined);
  assert.equal(seen.headers['x-sazu-contract'],VERSION);assert.equal(seen.path,'/internal/v1/calendar');
});

for(const token of [undefined,'wrong',INTERNAL]) test(`rejects missing/wrong/public-internal token ${token?.slice(0,3)}`,async t=>{
  let called=false;const {url}=await fixture(t,(req,res)=>{called=true;reply(req,res)});
  const r=await post(url,BODY,token?{...AUTH,authorization:`Bearer ${token}`}:{'content-type':'application/json'});
  assert.equal(r.status,401);assert.equal(called,false);
});

for(const body of ['{','null','[]',JSON.stringify({...BODY,year:true}),JSON.stringify({...BODY,path:'/etc/passwd'}),
                   JSON.stringify({...BODY,production_authorized:true}),JSON.stringify({...BODY,kind:'chinese_lunar'})]) {
 test(`invalid request ${body.slice(0,50)}`,async t=>{
   let called=false;const {url}=await fixture(t,(req,res)=>{called=true;reply(req,res)});
   const r=await post(url,body);assert.equal(r.status,422);assert.equal(called,false);
 });
}

test('keeps duplicate-key raw bytes for strict Python rejection',async t=>{
  let seen='';const raw='{"kind":"gregorian","year":2024,"year":2024,"month":2,"day":10}';
  const {url}=await fixture(t,async(req,res)=>{for await(const c of req) seen+=c;reply(req,res)});
  await post(url,raw);assert.equal(seen,raw);
});

test('media, compression and byte limits enforced',async t=>{
  const {url}=await fixture(t);
  assert.equal((await post(url,'{}',{...AUTH,'content-type':'text/plain'})).status,415);
  assert.equal((await post(url,'{}',{...AUTH,'content-encoding':'gzip'})).status,415);
  assert.equal((await post(url,'x'.repeat(16385))).status,413);
});

for(const [name,handler,expected] of [
 ['wrong-version',(req,res)=>reply(req,res,{contract_version:'other'}),502],
 ['production-claim',(req,res)=>reply(req,res,{production_authorized:true}),502],
 ['missing-result',(req,res)=>reply(req,res,{result:undefined}),502],
 ['invalid-result',(req,res)=>reply(req,res,{result:{made_up:'fortune'}}),502],
 ['wrong-correlation',(req,res)=>reply(req,res,{request_id:'different'}),502],
 ['wrong-request-echo',(req,res)=>reply(req,res,{result:calendarResult({...BODY,year:2023})}),502],
 ['private-error',(req,res)=>{res.writeHead(500);res.end('secret birth data')},503],
 ['internal-auth-failure',(req,res)=>{res.writeHead(401);res.end('private key')},502],
 ['bad-json',(req,res)=>{res.writeHead(200,{'content-type':'application/json'});res.end('{')},502],
 ['html',(req,res)=>{res.writeHead(200,{'content-type':'text/html'});res.end('private')},502],
 ['oversized',(req,res)=>{res.writeHead(200,{'content-type':'application/json'});res.end('x'.repeat(262145))},502],
 ['hang-before-headers',()=>{},504],
 ['hang-in-body',(req,res)=>{res.writeHead(200,{'content-type':'application/json'});res.write('{')},504],
]) test(`bounded upstream: ${name}`,async t=>{
  const {url}=await fixture(t,handler);const r=await post(url);
  assert.equal(r.status,expected);const text=await r.text();
  assert.ok(!text.includes('secret birth')&&!text.includes('private key'));
  assert.ok(!text.includes(INTERNAL)&&!text.includes(CLIENT));
});

test('does not follow upstream redirect or send credential elsewhere',async t=>{
  let reached=false;const target=await serve(t,(req,res)=>{reached=true;res.end('bad')});
  const {url}=await fixture(t,(req,res)=>{res.writeHead(302,{location:target});res.end()});
  assert.equal((await post(url)).status,502);assert.equal(reached,false);
});

test('safe domain error survives without arbitrary upstream message',async t=>{
  const {url}=await fixture(t,(req,res)=>{
    res.writeHead(422,{'content-type':'application/json'});
    res.end(JSON.stringify({ok:false,contract_version:VERSION,production_authorized:false,
      request_id:req.headers['x-request-id'],error:{code:'INVALID_INPUT',message:'PRIVATE',retryable:false}}));
  });
  const r=await post(url);assert.equal(r.status,422);const b=await r.json();
  assert.equal(b.error.code,'INVALID_INPUT');assert.ok(!JSON.stringify(b).includes('PRIVATE'));
});

test('health liveness is separate from authenticated dependent readiness',async t=>{
  const {url}=await fixture(t,(req,res)=>{
    res.writeHead(200,{'content-type':'application/json'});
    res.end(JSON.stringify({ok:true,contract_version:VERSION,production_authorized:false,
      request_id:req.headers['x-request-id'],status:'ready'}));
  });
  assert.equal((await fetch(url+'/health/live')).status,200);
  assert.equal((await fetch(url+'/health/ready')).status,401);
  assert.equal((await fetch(url+'/health/ready',{headers:AUTH})).status,200);
});

test('database failure makes readiness unavailable and does not leak DSN',async t=>{
  const {url}=await fixture(t,(req,res)=>reply(req,res,{status:'ready'}),
    {dependencies:{checkDatabase:async()=>{throw Error('postgres://secret-password')}}});
  const r=await fetch(url+'/health/ready',{headers:AUTH});assert.equal(r.status,503);
  assert.ok(!(await r.text()).includes('secret-password'));
});

test('arbitrary core admin operations not publicly routable',async t=>{
  const {url}=await fixture(t);
  for(const path of ['/v1/research/acquire-source','/v1/pillars','/internal/v1/calendar','/docs']) {
    assert.equal((await fetch(url+path,{method:'POST',headers:AUTH,body:'{}'})).status,404);
  }
});

test('bounded concurrent requests fail fast',async t=>{
  const {url}=await fixture(t,()=>{},{env:{MAX_IN_FLIGHT:'1',PYTHON_TIMEOUT_MS:'400'}});
  const first=post(url);await new Promise(r=>setTimeout(r,40));
  assert.equal((await post(url)).status,503);assert.equal((await first).status,504);
});

for(const env of [
 {RESEARCH_API_TOKEN:''},{CALCULATOR_TOKEN:CLIENT},{SAZU_MODE:'production'},
 {PYTHON_BASE_URL:'https://example.com'}, {PYTHON_BASE_URL:'http://127.0.0.1:8000?secret=x'},
 {PYTHON_BASE_URL:'http://user:password@127.0.0.1:8000'}, {PYTHON_TIMEOUT_MS:'0'},
 {MAX_IN_FLIGHT:'Infinity'}, {DATABASE_URL:''},
]) test(`configuration fails closed ${Object.keys(env)[0]} ${JSON.stringify(env).length}`,async()=>{
  const {loadConfig}=await modules();
  assert.throws(()=>loadConfig({SAZU_MODE:'research',RESEARCH_API_TOKEN:CLIENT,CALCULATOR_TOKEN:INTERNAL,
    PYTHON_BASE_URL:'http://calculator:8000',DATABASE_URL:'postgresql://sazu:fixture@postgres/sazu',...env}),/configuration/);
});

test('UTF-8 BOM must not be silently stripped from strict input',async t=>{
  const {url}=await fixture(t);
  assert.equal((await post(url,'\ufeff'+JSON.stringify(BODY))).status,422);
});

test('duplicate public authorization headers are rejected',async t=>{
  const {url}=await fixture(t);
  const status=await new Promise((resolve,reject)=>{
    const req=http.request(url+PATH,{method:'POST',headers:[
      'host',new URL(url).host,'authorization',`Bearer ${CLIENT}`,'authorization',`Bearer ${CLIENT}`,
      'content-type','application/json']},res=>{res.resume();resolve(res.statusCode)});
    req.on('error',reject);req.end(JSON.stringify(BODY));
  });
  assert.equal(status,401);
});

test('database readiness timeout is bounded even when checker never resolves',async t=>{
  const {url}=await fixture(t,(req,res)=>{
    res.writeHead(200,{'content-type':'application/json'});res.end(JSON.stringify({ok:true,
      request_id:req.headers['x-request-id'],contract_version:VERSION,production_authorized:false,status:'ready'}));
  },{env:{PYTHON_TIMEOUT_MS:'50'},dependencies:{checkDatabase:()=>new Promise(()=>{})}});
  const start=performance.now();assert.equal((await fetch(url+'/health/ready',{headers:AUTH})).status,503);
  assert.ok(performance.now()-start<1000);
});

test('client disconnect releases in-flight slot and aborts private request',async t=>{
  let calls=0,started;const ready=new Promise(r=>{started=r});
  const {url}=await fixture(t,(req,res)=>{if(++calls===1)started();else reply(req,res)},
    {env:{MAX_IN_FLIGHT:'1',PYTHON_TIMEOUT_MS:'2000'}});
  const controller=new AbortController();
  const pending=fetch(url+PATH,{method:'POST',headers:AUTH,body:JSON.stringify(BODY),signal:controller.signal}).catch(()=>null);
  await ready;controller.abort();await pending;await new Promise(r=>setTimeout(r,50));
  assert.equal((await post(url)).status,200);
});

test('per-process request budget is bounded',async t=>{
  const {url}=await fixture(t,undefined,{env:{RATE_LIMIT_PER_MINUTE:'1'}});
  assert.equal((await post(url)).status,200);
  assert.equal((await post(url)).status,429);
});

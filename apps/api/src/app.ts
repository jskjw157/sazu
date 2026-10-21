import express, {type Request,type Response,type NextFunction} from 'express';
import {createHash,randomUUID,timingSafeEqual} from 'node:crypto';
import type {Config} from './config.js';
import {CONTRACT,MAX_BODY,validInput,type Operation} from './contracts.js';
import {callPython,GatewayError} from './python-client.js';

interface Dependencies { checkDatabase:()=>Promise<void>; }
const digest=(value:string)=>createHash('sha256').update(value).digest();
const messages:Record<string,string>={
  UNAUTHORIZED:'Authentication required.',INVALID_INPUT:'Input does not satisfy the contract.',
  UNSUPPORTED_MEDIA_TYPE:'Use uncompressed UTF-8 JSON.',REQUEST_TOO_LARGE:'Request exceeds the allowed size.',
  CALCULATOR_TIMEOUT:'Calculation service deadline exceeded.',CALCULATOR_UNAVAILABLE:'Calculation service unavailable.',
  UPSTREAM_PROTOCOL_ERROR:'Invalid calculation service response.',UPSTREAM_AUTH_FAILED:'Internal service authentication failed.',
  NOT_READY:'Dependencies are not ready.',BUSY:'Service is at capacity.',RATE_LIMITED:'Request limit exceeded.',
  NOT_FOUND:'Endpoint not found.',INTERNAL_ERROR:'The operation could not be completed.'};
function fail(res:Response,code:string,status:number) {
  return res.status(status).json({ok:false,contract_version:CONTRACT,production_authorized:false,
    request_id:res.locals.requestId,error:{code,message:messages[code]??'Calculation could not be completed.',
      retryable:['CALCULATOR_TIMEOUT','CALCULATOR_UNAVAILABLE','BUSY','NOT_READY','RATE_LIMITED'].includes(code)}});
}
export function createApp(config:Config,dependencies:Dependencies) {
  const app=express();app.disable('x-powered-by');app.set('trust proxy',false);
  let active=0,tokens=config.rateLimit,last=performance.now();
  const expected=digest(`Bearer ${config.publicToken}`);
  app.use((_req,res,next)=>{
    res.locals.requestId=randomUUID();res.set({'cache-control':'no-store','x-content-type-options':'nosniff',
      'x-request-id':res.locals.requestId,'x-sazu-contract':CONTRACT});next();
  });
  app.get('/health/live',(_req,res)=>{res.json({ok:true,status:'alive',contract_version:CONTRACT,
    production_authorized:false,request_id:res.locals.requestId});});
  function authorize(req:Request,res:Response,next:NextFunction) {
    const now=performance.now();tokens=Math.min(config.rateLimit,tokens+(now-last)*config.rateLimit/60000);last=now;
    if(tokens<1) {fail(res,'RATE_LIMITED',429);return;}tokens-=1;
    const count=req.rawHeaders.filter((v,i)=>i%2===0&&v.toLowerCase()==='authorization').length;
    if(count!==1||!timingSafeEqual(digest(req.headers.authorization??''),expected)) {fail(res,'UNAUTHORIZED',401);return;}
    next();
  }
  function bounded(handler:(req:Request,res:Response,signal:AbortSignal)=>Promise<void>) {
    return async(req:Request,res:Response)=>{
      if(active>=config.maxInFlight) {fail(res,'BUSY',503);return;}
      active+=1;const controller=new AbortController();
      const onClose=()=>{if(!res.writableEnded)controller.abort();};res.on('close',onClose);
      try {await handler(req,res,controller.signal);}
      catch(e) {
        if(!res.destroyed&&!res.headersSent) {
          if(e instanceof GatewayError) fail(res,e.code,e.status);
          else fail(res,'INTERNAL_ERROR',500);
        }
      } finally {controller.abort();res.off('close',onClose);active-=1;}
    };
  }
  app.get('/health/ready',authorize,bounded(async(_req,res,signal)=>{
    let timer:NodeJS.Timeout|undefined;
    try {
      await Promise.all([callPython(config,'ready',undefined,res.locals.requestId,signal),
        Promise.race([dependencies.checkDatabase(),new Promise<never>((_,reject)=>{
          timer=setTimeout(()=>reject(new GatewayError('NOT_READY',503)),config.timeoutMs);timer.unref();
        })])]);
      res.json({ok:true,status:'ready',contract_version:CONTRACT,production_authorized:false,request_id:res.locals.requestId});
    } catch {throw new GatewayError('NOT_READY',503);}
    finally {if(timer)clearTimeout(timer);}
  }));
  const rawParser=express.raw({type:()=>true,limit:MAX_BODY,inflate:false});
  for(const op of ['calendar','normalize-time'] as const) {
    app.post(`/v1/research/${op}`,authorize,(req,res,next)=>{
      if(!/^application\/json(?:\s*;\s*charset=utf-8)?$/i.test(req.headers['content-type']??'')
         ||(req.headers['content-encoding']??'identity')!=='identity') {fail(res,'UNSUPPORTED_MEDIA_TYPE',415);return;}
      next();
    },rawParser,bounded(async(req,res,signal)=>{
      let raw:string,value:unknown;
      try {raw=new TextDecoder('utf-8',{fatal:true,ignoreBOM:true}).decode(req.body);value=JSON.parse(raw);}
      catch {throw new GatewayError('INVALID_INPUT',422);}
      if(!validInput(op as Operation,value)||Object.keys(req.query).length) throw new GatewayError('INVALID_INPUT',422);
      const result=await callPython(config,op,raw,res.locals.requestId,signal);res.status(200).json(result);
    }));
  }
  app.use((_req,res)=>{fail(res,'NOT_FOUND',404);});
  app.use((error:unknown,_req:Request,res:Response,_next:NextFunction)=>{
    if(res.headersSent) {res.end();return;}
    const e=error as {type?:string;status?:number};
    if(e.type==='entity.too.large') fail(res,'REQUEST_TOO_LARGE',413);
    else if(e.status===415)fail(res,'UNSUPPORTED_MEDIA_TYPE',415);
    else fail(res,'INVALID_INPUT',422);
  });
  return app;
}

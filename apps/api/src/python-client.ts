/** Bounded transport to one configured private service, with no redirect/retry. */
import type { Config } from './config.js';
import { CONTRACT, MAX_RESPONSE, validOutput, validError, matchesRequest, type Operation } from './contracts.js';
export class GatewayError extends Error {
  constructor(public readonly code:string,public readonly status:number) {super(code);}
}
export function domainStatus(code:string):number {
  return ['INVALID_INPUT','UNSUPPORTED_RANGE','NONEXISTENT_LOCAL_TIME','UNSUPPORTED_TIMEZONE_RULE'].includes(code)?422:
    code==='REQUEST_TOO_LARGE'?413:503;
}
export async function callPython(config:Config,op:Operation|'ready',raw:string|undefined,
                                requestId:string,parent:AbortSignal):Promise<Record<string,unknown>> {
  const deadline=new AbortController();
  const timer=setTimeout(()=>deadline.abort(),config.timeoutMs);timer.unref();
  const signal=AbortSignal.any([deadline.signal,parent]);
  let response:Response|undefined;
  try {
    response=await fetch(config.pythonBaseUrl+(op==='ready'?'/health/ready':`/internal/v1/${op}`),{
      method:op==='ready'?'GET':'POST', redirect:'manual', signal,
      headers:{authorization:`Bearer ${config.internalToken}`,'content-type':'application/json',
        'x-sazu-contract':CONTRACT,'x-request-id':requestId},
      ...(raw===undefined?{}:{body:raw})});
    if(response.status>=300&&response.status<400) throw new GatewayError('UPSTREAM_PROTOCOL_ERROR',502);
    if(response.status===401||response.status===403) throw new GatewayError('UPSTREAM_AUTH_FAILED',502);
    if(response.status>=500) throw new GatewayError('CALCULATOR_UNAVAILABLE',503);
    if(!/^application\/json(?:\s*;.*)?$/i.test(response.headers.get('content-type')??''))
      throw new GatewayError('UPSTREAM_PROTOCOL_ERROR',502);
    if(Number(response.headers.get('content-length'))>MAX_RESPONSE)
      throw new GatewayError('UPSTREAM_PROTOCOL_ERROR',502);
    const reader=response.body?.getReader();
    if(!reader) throw new GatewayError('UPSTREAM_PROTOCOL_ERROR',502);
    const chunks:Uint8Array[]=[];let bytes=0;
    try {
      while(true) {
        const {done,value}=await reader.read();if(done) break;
        bytes+=value.length;if(bytes>MAX_RESPONSE) throw new GatewayError('UPSTREAM_PROTOCOL_ERROR',502);
        chunks.push(value);
      }
    } finally { void reader.cancel().catch(()=>{}); }
    let value:Record<string,unknown>;
    try {value=JSON.parse(new TextDecoder('utf-8',{fatal:true,ignoreBOM:true}).decode(Buffer.concat(chunks))) as Record<string,unknown>;}
    catch {throw new GatewayError('UPSTREAM_PROTOCOL_ERROR',502);}
    if(typeof value!=='object'||value===null||value.request_id!==requestId)
      throw new GatewayError('UPSTREAM_PROTOCOL_ERROR',502);
    if(response.status===200&&validOutput(op,value)) {
      if(op!=='ready'&&!matchesRequest(op,value.result as Record<string,unknown>,JSON.parse(raw!)))
        throw new GatewayError('UPSTREAM_PROTOCOL_ERROR',502);
      return value;
    }
    if(response.status!==200&&validError(value)) {
      const code=(value.error as Record<string,unknown>).code as string;
      if(domainStatus(code)===response.status) throw new GatewayError(code,response.status);
    }
    throw new GatewayError('UPSTREAM_PROTOCOL_ERROR',502);
  } catch(error) {
    if(deadline.signal.aborted) throw new GatewayError('CALCULATOR_TIMEOUT',504);
    if(parent.aborted) throw new GatewayError('REQUEST_CANCELLED',499);
    if(error instanceof GatewayError) throw error;
    throw new GatewayError('CALCULATOR_UNAVAILABLE',503);
  } finally {
    clearTimeout(timer);
    if(response?.body&&!response.body.locked) void response.body.cancel().catch(()=>{});
  }
}

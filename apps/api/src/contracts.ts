/** Transport schemas only. No astronomy, lunar or timezone rules are duplicated here. */
import { Ajv } from 'ajv';
export const CONTRACT = 'sazu.foundation.v1';
export const MAX_BODY = 16384, MAX_RESPONSE = 262144;
export type Operation = 'calendar' | 'normalize-time';
const ajv = new Ajv({allErrors:false,coerceTypes:false,removeAdditional:false,strict:true});
const str = {type:'string',minLength:1,maxLength:200};
const date = {type:'string',pattern:'^[0-9]{4}-[0-9]{2}-[0-9]{2}$'};
const timestamp = {type:'string',pattern:'^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\\.[0-9]{1,6})?Z$'};
const int = (min:number,max:number)=>({type:'integer',minimum:min,maximum:max});
const obj = (properties:Record<string,unknown>,required=Object.keys(properties))=>
  ({type:'object',properties,required,additionalProperties:false});
const calendarFields = {kind:{enum:['gregorian','korean_lunar']},year:int(1,9999),month:int(1,12),day:int(1,31),
  leap:{enum:['regular','leap','unknown',null]}};
const timeFields = {
  local_date:date, zone:str, precision:{enum:['instant','minute_bucket','rounded_minute','interval','unknown']},
  local_time:{type:'string',pattern:'^[0-9]{2}:[0-9]{2}(:[0-9]{2}(\\.[0-9]{1,6})?)?$'},
  end_local:{type:'string',pattern:'^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}(:[0-9]{2}(\\.[0-9]{1,6})?)?$'},
  start_inclusive:{type:'boolean'},end_inclusive:{type:'boolean'},fold:int(0,1),
};
const requestSchemas = {
  calendar:obj(calendarFields,['kind','year','month','day']),
  'normalize-time':obj(timeFields,['local_date','zone','precision']),
};
const sha = {type:'string',pattern:'^[a-f0-9]{64}$'};
const results = {
  calendar: obj({request:obj(calendarFields),candidates:{type:'array',minItems:1,maxItems:2,items:
    obj({solar:date,lunar_year:int(1,9999),lunar_month:int(1,12),lunar_day:int(1,30),is_leap:{type:'boolean'}})},
    library_version:str,library_sha256:sha,evidence_level:{const:'library_regression_not_official_verification'}}),
  'normalize-time':obj({precision:timeFields.precision,zone:str,
    intervals:{type:'array',minItems:1,maxItems:128,items:obj({start:timestamp,end:timestamp,
      start_inclusive:{type:'boolean'},end_inclusive:{type:'boolean'}})},
    tzdata_version:str,iana_version:str,zone_sha256:sha,
    warnings:{type:'array',maxItems:8,uniqueItems:true,items:{enum:['AMBIGUOUS_LOCAL_TIME','PARTIAL_LOCAL_GAP']}},
    evidence_level:{const:'pinned_timezone_computation_not_production_approval'}}),
};
const common = {contract_version:{const:CONTRACT},production_authorized:{const:false},
  request_id:{type:'string',pattern:'^[0-9a-f-]{36}$'}};
export const domainErrors = ['INVALID_INPUT','UNSUPPORTED_RANGE','NONEXISTENT_LOCAL_TIME',
  'UNSUPPORTED_TIMEZONE_RULE','SOURCE_NOT_AVAILABLE','DATA_INTEGRITY_FAILED','RELEASE_NOT_APPROVED',
  'SOURCE_CONFLICT','REQUEST_TOO_LARGE','INTERNAL_ERROR','UNAUTHORIZED','CONTRACT_MISMATCH','BUSY'];
const errorSchema = obj({...common,ok:{const:false},error:obj({code:{enum:domainErrors},
  message:{type:'string',maxLength:512},retryable:{type:'boolean'}})});
const inputs = {calendar:ajv.compile(requestSchemas.calendar),'normalize-time':ajv.compile(requestSchemas['normalize-time'])};
const envelopes = {calendar:ajv.compile(obj({...common,ok:{const:true},result:results.calendar})),
  'normalize-time':ajv.compile(obj({...common,ok:{const:true},result:results['normalize-time']})),
  ready:ajv.compile(obj({...common,ok:{const:true},status:{const:'ready'}}))};
const errorValidator = ajv.compile(errorSchema);
export function validInput(op:Operation,value:unknown):boolean { return inputs[op](value) as boolean; }
export function validOutput(op:Operation|'ready',value:unknown):boolean { return envelopes[op](value) as boolean; }
export function validError(value:unknown):boolean { return errorValidator(value) as boolean; }
export function matchesRequest(op:Operation,result:Record<string,unknown>,input:Record<string,unknown>):boolean {
  if (op==='normalize-time') return result.zone===input.zone && result.precision===input.precision;
  const request=result.request as Record<string,unknown>;
  return ['kind','year','month','day'].every(k=>request[k]===input[k])
    && request.leap===(input.leap??null);
}

/** Process entrypoint. PostgreSQL belongs to Express, never to the calculator. */
import http from 'node:http';
import pg from 'pg';
import {loadConfig} from './config.js';
import {createApp} from './app.js';

async function main() {
  const config=loadConfig();
  const pool=new pg.Pool({connectionString:config.databaseUrl,max:4,
    connectionTimeoutMillis:2000,idleTimeoutMillis:10000,statement_timeout:2000,
    query_timeout:2500,application_name:'sazu-api'});
  pool.on('error',()=>{console.error('database_connection_error');});
  const app=createApp(config,{checkDatabase:async()=>{await pool.query('SELECT 1');}});
  const server=http.createServer({requestTimeout:10000,headersTimeout:5000,
    connectionsCheckingInterval:1000,maxHeaderSize:8192},app);
  server.keepAliveTimeout=5000;server.maxRequestsPerSocket=100;
  let stopping=false;
  const stop=()=>{
    if(stopping)return;stopping=true;
    const force=setTimeout(()=>{server.closeAllConnections();process.exit(1);},10000);force.unref();
    server.close(()=>{void pool.end().then(()=>{clearTimeout(force);}).catch(()=>{process.exitCode=1;});});
    server.closeIdleConnections();
  };
  process.once('SIGTERM',stop);process.once('SIGINT',stop);
  server.once('error',()=>{console.error('http_server_error');stop();process.exitCode=1;});
  server.listen(config.port,config.host,()=>{console.info('sazu_gateway_started_research_only');});
}
void main().catch(()=>{console.error('service_startup_failed');process.exitCode=1;});

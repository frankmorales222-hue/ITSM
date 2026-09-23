import {FormEvent, useCallback, useEffect, useState} from 'react'
import {api} from './api'
import './endpoint-actions.css'

type Action={id:number;ticket_id?:number;ticket_number?:string;ticket_subject?:string;action_type:string;target:string;status:string;result_summary?:string;auto_approved?:boolean;auto_approval_reason?:string;retry_count?:number;created_at:string}
type Props={ticket:{id:number;requester_id:number;assigned_user_id?:number;status:string};user:{id:number;role:string}}
const staffRoles=['technician','team_lead','manager','admin']

export function TicketEndpointSummary({ticket}:{ticket:Props['ticket']}){
 const [agent,setAgent]=useState<any>(null)
 useEffect(()=>{let active=true;api(`/tickets/${ticket.id}/endpoint-actions`).then(result=>{if(active)setAgent(result.agent)}).catch(()=>{if(active)setAgent(null)});return()=>{active=false}},[ticket.id])
 if(!agent)return <div className="ticket-endpoint-summary"><span>ASSET INFORMATION</span><strong>No linked endpoint</strong><small>An endpoint agent has not reported for this requester.</small></div>
 const cpu=agent.cpu_percent===null||agent.cpu_percent===undefined?'Not reported':`${agent.cpu_percent}%`
 const memory=agent.memory_percent===null||agent.memory_percent===undefined?'Not reported':`${agent.memory_percent}%`
 return <div className="ticket-endpoint-summary"><span>ASSET INFORMATION</span><strong>{agent.hostname||'Endpoint reported'}</strong><small>CPU {cpu} · Memory {memory}</small><small>{agent.operating_system||'Operating system not reported'}{agent.os_version?` (${agent.os_version})`:''}</small></div>
}

export function EndpointActions({ticket,user}:Props){
 const [agent,setAgent]=useState<any>(null),[actions,setActions]=useState<Action[]>([]),[kind,setKind]=useState('terminate_process'),[target,setTarget]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('')
 const isStaff=staffRoles.includes(user.role),isRequester=user.id===ticket.requester_id
 const hasActiveAction=actions.some(item=>['Pending approval','Approved','Dispatched'].includes(item.status))
 const load=useCallback(async()=>{try{const result=await api(`/tickets/${ticket.id}/endpoint-actions`);setAgent(result.agent);setActions(result.actions||[])}catch(e:any){setError(e.message)}},[ticket.id])
 useEffect(()=>{load()},[load])
 useEffect(()=>{if(!hasActiveAction)return;const refresh=()=>{if(!document.hidden)load()};const timer=setInterval(refresh,5000);addEventListener('focus',refresh);document.addEventListener('visibilitychange',refresh);return()=>{clearInterval(timer);removeEventListener('focus',refresh);document.removeEventListener('visibilitychange',refresh)}},[hasActiveAction,load])
 async function request(e:FormEvent){e.preventDefault();setBusy(true);setError('');try{await api(`/tickets/${ticket.id}/endpoint-actions`,{method:'POST',body:JSON.stringify({action_type:kind,target:target.trim()})});setTarget('');await load()}catch(e:any){setError(e.message)}finally{setBusy(false)}}
 async function decide(id:number,decision:'approve'|'decline'){setBusy(true);setError('');try{await api(`/tickets/${ticket.id}/endpoint-actions/${id}/${decision}`,{method:'POST'});await load()}catch(e:any){setError(e.message)}finally{setBusy(false)}}
 if(!agent&&!isStaff)return null
 return <section className="endpoint-actions"><header><div><p className="eyebrow">Remote support action</p><h3>Request endpoint approval</h3><small>{agent?`Connected to ${agent.hostname}. The requester must approve before the action runs.`:"No endpoint agent found on this requester's computer."}</small></div></header>{error&&<div className="alert danger">{error}</div>}{isStaff&&agent&&!['Closed','Cancelled'].includes(ticket.status)&&<form onSubmit={request}><label>Approved action<select value={kind} onChange={e=>setKind(e.target.value)}><option value="terminate_process">Close a hung application</option><option value="restart_service">Restart a Windows service</option></select></label><label>{kind==='terminate_process'?'Application executable':'Windows service name'}<input required value={target} onChange={e=>setTarget(e.target.value)} placeholder={kind==='terminate_process'?'EXCEL.EXE':'Spooler'}/></label><button className="primary" disabled={busy||!target.trim()}>Request user approval</button><small>The agent runs this only after the requester approves it.</small></form>}{actions.length>0&&<div className="endpoint-action-list">{actions.map(action=><article key={action.id}><div><strong>{action.action_type==='terminate_process'?'Close application':'Restart service'}: {action.target}</strong>{action.auto_approved&&<span className="badge auto-approved">Auto-approved for frozen app</span>}<small>{action.status}{action.result_summary?` - ${action.result_summary}`:''}</small>{!!action.retry_count&&<small className="action-retry">Attempt {action.retry_count}/5</small>}</div>{isRequester&&action.status==='Pending approval'&&<div><button className="primary" disabled={busy} onClick={()=>decide(action.id,'approve')}>Approve</button><button disabled={busy} onClick={()=>decide(action.id,'decline')}>Decline</button></div>}</article>)}</div>}</section>
}

export function EndpointActionsAuto({ticket}:{ticket:Props['ticket']}){
 const [user,setUser]=useState<Props['user']|null>(null)
 useEffect(()=>{api('/auth/me').then(result=>setUser(result.user)).catch(()=>setUser(null))},[ticket.id])
 return user?<EndpointActions ticket={ticket} user={user}/>:null
}

export function PendingEndpointApprovalWatcher({user,onOpen}:{user:Props['user'];onOpen:(ticketId:number)=>void}){
 const [pending,setPending]=useState<Action[]>([]),[busy,setBusy]=useState(false),[error,setError]=useState('')
 const load=useCallback(async()=>{if(document.hidden)return;try{setPending(await api('/endpoint-actions/pending'))}catch{}},[user.id])
 useEffect(()=>{setPending([]);load();const timer=setInterval(load,5000);addEventListener('focus',load);document.addEventListener('visibilitychange',load);return()=>{clearInterval(timer);removeEventListener('focus',load);document.removeEventListener('visibilitychange',load)}},[load])
 const action=pending[0]
 if(!action||!action.ticket_id)return null
 async function decide(decision:'approve'|'decline'){setBusy(true);setError('');try{await api(`/tickets/${action.ticket_id}/endpoint-actions/${action.id}/${decision}`,{method:'POST'});setPending(current=>current.filter(item=>item.id!==action.id))}catch(e:any){setError(e.message);await load()}finally{setBusy(false)}}
 const label=action.action_type==='terminate_process'?'close application':'restart service'
 return <aside className="endpoint-approval-prompt" role="alertdialog" aria-live="assertive" aria-label="Endpoint action approval required"><p className="eyebrow">Your approval is required</p><h3>{action.ticket_number}: {action.ticket_subject}</h3><p>Your technician wants to {label} <strong>{action.target}</strong>.</p>{error&&<div className="alert danger">{error}</div>}<div><button onClick={()=>onOpen(action.ticket_id!)}>Open ticket</button><button disabled={busy} onClick={()=>decide('decline')}>Decline</button><button className="primary" disabled={busy} onClick={()=>decide('approve')}>{busy?'Saving...':'Approve'}</button></div>{pending.length>1&&<small>{pending.length-1} more approval request{pending.length===2?'':'s'} waiting</small>}</aside>
}

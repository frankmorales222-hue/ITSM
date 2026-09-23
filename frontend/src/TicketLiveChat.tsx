import {useEffect, useRef, useState} from 'react'
import {api} from './api'
import {EndpointActionsAuto} from './EndpointActions'

type ChatMessage={id:number;body:string;author_id:number|null;author:string;created_at:string;source:string}
type ChatSession={id:number;ticket_id:number;ticket_number:string;requester_id:number;requester:string;assigned_user_id:number;assigned_user?:string;requested_by_id:number;status:string;requested_at:string;messages?:ChatMessage[]}
type ChatTicket={id:number;status:string;requester_id:number;assigned_user_id?:number}
type ChatUser={id:number;role:string}
const closedTickets=['Closed','Cancelled']
const when=(value:string)=>new Intl.DateTimeFormat(undefined,{hour:'numeric',minute:'2-digit'}).format(new Date(value))

export function TicketLiveChat({ticket,user}:{ticket:ChatTicket;user:ChatUser}){
 const [session,setSession]=useState<ChatSession|null>(null),[messages,setMessages]=useState<ChatMessage[]>([]),[body,setBody]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false),bottom=useRef<HTMLDivElement>(null)
 const participant=user.id===ticket.requester_id||user.id===ticket.assigned_user_id
 async function load(){if(!participant)return;try{const result=await api(`/tickets/${ticket.id}/chat`);setSession(result.session);setMessages(result.session?.messages||[])}catch(e:any){if(!String(e.message).includes('not found'))setError(e.message)}}
 useEffect(()=>{setSession(null);setMessages([]);setError('');load()},[ticket.id,ticket.assigned_user_id,user.id])
 useEffect(()=>{if(!participant||session)return;const refresh=()=>{if(!document.hidden)load()};const timer=setInterval(refresh,4000);addEventListener('focus',refresh);document.addEventListener('visibilitychange',refresh);return()=>{clearInterval(timer);removeEventListener('focus',refresh);document.removeEventListener('visibilitychange',refresh)}},[participant,session?.id,ticket.id])
 useEffect(()=>{if(!session||session.status==='closed')return;let stopped=false;const poll=async()=>{if(document.hidden||stopped)return;try{const after=messages.length?messages[messages.length-1].id:0;const result=await api(`/chat/${session.id}/messages?after_id=${after}`);if(!stopped&&result.messages.length)setMessages(current=>[...current,...result.messages.filter((item:ChatMessage)=>!current.some(saved=>saved.id===item.id))]);if(!stopped&&result.status!==session.status)setSession(current=>current?{...current,status:result.status}:current)}catch{}};const timer=setInterval(poll,3000);return()=>{stopped=true;clearInterval(timer)}},[session?.id,session?.status,messages.length])
 // Keep scrolling inside the transcript. scrollIntoView can move the entire
 // single-page application out of view in managed Chromium environments.
 useEffect(()=>{const transcript=bottom.current?.parentElement;if(transcript){transcript.scrollTop=transcript.scrollHeight}},[messages.length])
 if(!participant)return null
 async function request(){setBusy(true);setError('');try{const result=await api(`/tickets/${ticket.id}/chat/request`,{method:'POST'});setSession(result);setMessages(result.messages||[])}catch(e:any){setError(e.message)}finally{setBusy(false)}}
 async function accept(){if(!session)return;setBusy(true);try{const result=await api(`/chat/${session.id}/accept`,{method:'POST'});setSession(result);setMessages(result.messages||[])}catch(e:any){setError(e.message)}finally{setBusy(false)}}
 async function send(){if(!session||!body.trim()||busy)return;setBusy(true);setError('');try{const message=await api(`/chat/${session.id}/messages`,{method:'POST',body:JSON.stringify({body:body.trim(),client_message_id:crypto.randomUUID()})});setMessages(current=>current.some(item=>item.id===message.id)?current:[...current,message]);setBody('')}catch(e:any){setError(e.message)}finally{setBusy(false)}}
 async function close(){if(!session)return;setBusy(true);try{const result=await api(`/chat/${session.id}/close`,{method:'POST'});setSession(result);setMessages(result.messages||[])}catch(e:any){setError(e.message)}finally{setBusy(false)}}
 async function teams(){setBusy(true);setError('');try{const result=await api(`/tickets/${ticket.id}/teams-session`,{method:'POST'});const opened=window.open(result.join_url,'_blank','noopener,noreferrer');if(!opened)location.assign(result.join_url)}catch(e:any){setError(e.message)}finally{setBusy(false)}}
 if(!session&&!closedTickets.includes(ticket.status))return <section className="ticket-live-chat callout"><div><p className="eyebrow">Live support</p><h3>{user.role==='end_user'?'Chat with your assigned technician':'Contact the requester'}</h3><p>Every message is saved securely in this ticket.</p>{error&&<div className="alert danger">{error}</div>}</div><div className="live-support-actions"><button type="button" className="primary" disabled={busy||!ticket.assigned_user_id} onClick={request}>{ticket.assigned_user_id?(user.role==='end_user'?'Request live help':'Start live chat'):'Waiting for assignment'}</button>{user.role!=='end_user'&&<button type="button" disabled={busy} onClick={teams}>Start Teams session</button>}</div></section>
 if(!session)return null
 return <section className={`ticket-live-chat ${session.status}`} aria-label="Ticket live chat"><header><div><p className="eyebrow">Live support</p><h3>{session.status==='requested'?'Live help requested':session.status==='active'?'Live chat':'Chat transcript'}</h3><small>{session.status==='closed'?'This conversation is saved in the request timeline.':`Ticket ${session.ticket_number}`}</small></div><div>{user.id===ticket.assigned_user_id&&session.status!=='closed'&&<button type="button" onClick={teams} disabled={busy}>Start Teams session</button>}{session.status==='requested'&&user.id!==session.requested_by_id&&<button type="button" className="primary" onClick={accept} disabled={busy}>Join chat</button>}{session.status!=='closed'&&<button type="button" onClick={close} disabled={busy}>End chat</button>}</div></header>{error&&<div className="alert danger">{error}</div>}<div className="live-chat-messages" aria-live="polite">{messages.map(message=><article key={message.id} className={message.author_id===user.id?'mine':''}><strong>{message.author}</strong><p>{message.body}</p><time>{when(message.created_at)}</time></article>)}<div ref={bottom}/></div>{session.status!=='closed'&&<div className="live-chat-composer"><textarea maxLength={4000} value={body} onChange={event=>setBody(event.target.value)} placeholder="Write a live message…"/><div><small>{body.length}/4000 · Saved to this ticket</small><button type="button" className="primary" onClick={send} disabled={busy||!body.trim()}>Send</button></div></div>}</section>
}

export function TicketLiveChatAuto({ticket}:{ticket:ChatTicket}){
 const [user,setUser]=useState<ChatUser|null>(null)
 useEffect(()=>{api('/auth/me').then(result=>setUser(result.user)).catch(()=>setUser(null))},[ticket.id])
 return user?<><TicketLiveChat ticket={ticket} user={user}/><EndpointActionsAuto ticket={ticket}/></>:null
}

export function ChatInvitationWatcher({user,onOpen}:{user:ChatUser;onOpen:(ticketId:number)=>void}){
 const [invite,setInvite]=useState<ChatSession|null>(null),dismissed=useRef<Set<number>>(new Set())
 useEffect(()=>{dismissed.current.clear();setInvite(null);let stopped=false;const poll=async()=>{if(document.hidden||stopped)return;try{const rows=await api('/chat/invitations');const next=rows.find((item:ChatSession)=>!dismissed.current.has(item.id))||null;if(!stopped)setInvite(next)}catch{}};poll();const timer=setInterval(poll,5000);addEventListener('focus',poll);document.addEventListener('visibilitychange',poll);return()=>{stopped=true;clearInterval(timer);removeEventListener('focus',poll);document.removeEventListener('visibilitychange',poll)}},[user.id,user.role])
 if(!invite)return null
 return <aside className="chat-invitation" role="alertdialog" aria-label="Live help requested"><button className="chat-invitation-close" onClick={()=>{dismissed.current.add(invite.id);setInvite(null)}} aria-label="Dismiss">×</button><p className="eyebrow">Live help requested</p><h3>{invite.requester} is waiting</h3><p>Assigned ticket {invite.ticket_number}</p><button className="primary" onClick={()=>{dismissed.current.add(invite.id);onOpen(invite.ticket_id);setInvite(null)}}>Open chat</button></aside>
}

export function ChatInvitationRoot(){
 const [user,setUser]=useState<ChatUser|null>(null)
 useEffect(()=>{let stopped=false;const refresh=()=>api('/auth/me').then(result=>{if(!stopped)setUser(result.user)}).catch(()=>{if(!stopped)setUser(null)});refresh();const timer=setInterval(refresh,30000);return()=>{stopped=true;clearInterval(timer)}},[])
 return user?<ChatInvitationWatcher user={user} onOpen={ticketId=>{location.hash=`ticket/${ticketId}`}}/>:null
}

let csrf = sessionStorage.getItem('csrf') || ''
export const setCsrf = (value:string) => { csrf=value; sessionStorage.setItem('csrf',value) }
export async function api<T=any>(path:string, options:RequestInit={}):Promise<T>{
  const headers:Record<string,string>={'Content-Type':'application/json',...(options.headers as Record<string,string>||{})}
  if(csrf) headers['X-CSRF-Token']=csrf
  const response=await fetch(`/api${path}`,{...options,headers,credentials:'include'})
  const data=await response.json().catch(()=>({detail:response.statusText}))
  if(!response.ok) throw new Error(Array.isArray(data.detail)?data.detail.join('. '):(data.detail||'Request failed'))
  return data
}
export function login(username:string,password:string){return api('/auth/login',{method:'POST',body:JSON.stringify({username,password})})}
export function logout(){return api('/auth/logout',{method:'POST'})}


let csrf = sessionStorage.getItem('csrf') || ''
export const setCsrf = (value:string) => { csrf=value; sessionStorage.setItem('csrf',value) }

function readableError(detail:any):string {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map(item => {
    if (typeof item === 'string') return item
    const field = Array.isArray(item?.loc) ? item.loc.filter((part:any) => part !== 'body').join(' → ') : ''
    return [field, item?.msg || item?.message].filter(Boolean).join(': ') || JSON.stringify(item)
  }).join('. ')
  if (detail && typeof detail === 'object') return detail.message || detail.msg || JSON.stringify(detail)
  return 'Request failed'
}

export async function api<T=any>(path:string, options:RequestInit={}):Promise<T>{
  const headers:Record<string,string>={...(options.headers as Record<string,string>||{})}
  if(!(options.body instanceof FormData)) headers['Content-Type']='application/json'
  if(csrf) headers['X-CSRF-Token']=csrf
  const response=await fetch(`/api${path}`,{...options,headers,credentials:'include'})
  const data=await response.json().catch(()=>({detail:response.statusText}))
  if(!response.ok) throw new Error(readableError(data.detail ?? data))
  return data
}
export function login(username:string,password:string){return api('/auth/login',{method:'POST',body:JSON.stringify({username,password})})}
export function logout(){return api('/auth/logout',{method:'POST'})}

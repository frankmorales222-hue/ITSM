import {DragEvent, useMemo, useState} from 'react'
import {api} from './api'
import './visual-form-studio.css'
import './visual-form-studio-responsive.css'
import './visual-form-studio-enhancements.css'

type Field={
  id:string;key:string;label:string;type:string;required:boolean;help:string;options:string[];
  width?:'third'|'half'|'two_thirds'|'full';placeholder?:string;icon?:string;max_length?:number|null;
  visibility?:'visible'|'hidden'|'technician_only';read_only?:boolean;default_value?:any;
  show_when?:{key:string;value:string}|null;required_when?:{key:string;value:string}|null;
  classification?:'public'|'internal'|'restricted';mask_value?:boolean;access_roles?:string[];retention_days?:number|null;reportable?:boolean
}
type FormDef={id?:number;name:string;slug:string;description:string;category:string;icon:string;fields:Field[];active:boolean;is_template?:boolean;published:boolean;
  form_type?:string;portal_visible?:boolean;default_for_type?:boolean;requester_layout?:string[];technician_layout?:string[];lifecycle_state?:string;version?:number;archived_at?:string|null}
type FieldType={type:string;label:string;icon:string;group:string;defaultWidth:Field['width'];help:string}

const fieldTypes:FieldType[]=[
  {type:'section',label:'Section',icon:'§',group:'Layout',defaultWidth:'full',help:'Create a numbered heading that groups related questions and explains the purpose of the section.'},
  {type:'short_text',label:'Short text',icon:'T',group:'Text',defaultWidth:'half',help:'Collect a short, single-line answer such as a name, application, subject, or employee ID.'},
  {type:'long_text',label:'Long description',icon:'≡',group:'Text',defaultWidth:'full',help:'Collect detailed multi-line information such as symptoms, business justification, or troubleshooting steps.'},
  {type:'email',label:'Email',icon:'@',group:'Text',defaultWidth:'half',help:'Collect and validate an email address before the request can be submitted.'},
  {type:'phone',label:'Phone',icon:'☎',group:'Text',defaultWidth:'half',help:'Collect a telephone or callback number using a phone-friendly input.'},
  {type:'number',label:'Number',icon:'#',group:'Text',defaultWidth:'half',help:'Collect a numeric value such as quantity, cost, count, or duration.'},
  {type:'select',label:'Dropdown',icon:'⌄',group:'Choice',defaultWidth:'half',help:'Let the requester choose one answer from a compact list. Add as many options as needed in the inspector.'},
  {type:'choice_cards',label:'Choice cards',icon:'▦',group:'Choice',defaultWidth:'full',help:'Present one-choice options as large visual cards for important categories or request types.'},
  {type:'radio',label:'Radio group',icon:'◉',group:'Choice',defaultWidth:'half',help:'Show all single-choice answers at once. Best for short lists such as Low, Medium, and High.'},
  {type:'multi_select',label:'Multi-select',icon:'☷',group:'Choice',defaultWidth:'half',help:'Allow the requester to choose more than one option from a configured list.'},
  {type:'checkbox',label:'Checkbox',icon:'✓',group:'Choice',defaultWidth:'full',help:'Collect a yes/no confirmation, acknowledgement, permission, or required agreement.'},
  {type:'date',label:'Date',icon:'□',group:'Date & time',defaultWidth:'half',help:'Collect a calendar date such as an occurrence, start, due, or implementation date.'},
  {type:'time',label:'Time',icon:'◷',group:'Date & time',defaultWidth:'half',help:'Collect a time of day such as a callback time or planned change window.'},
  {type:'user',label:'Person',icon:'♙',group:'ITSM data',defaultWidth:'half',help:'Let staff select an active ITSM requester, manager, approver, or affected employee.'},
  {type:'asset',label:'Asset',icon:'◇',group:'ITSM data',defaultWidth:'half',help:'Let the requester select an asset from the connected inventory so it is linked to the ticket.'},
  {type:'attachment',label:'Attachments',icon:'↥',group:'ITSM data',defaultWidth:'full',help:'Allow up to 10 supporting files. Permitted files are stored securely and appear on Ticket Detail.'},
]

const id=()=>crypto.randomUUID()
const slug=(value:string)=>value.toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'')
const keyFrom=(value:string)=>value.toLowerCase().replace(/[^a-z0-9]+/g,'_').replace(/^_|_$/g,'').slice(0,60)
const blankForm=():FormDef=>({name:'',slug:'',description:'',category:'General',icon:'form',fields:[],active:true,is_template:false,published:false,form_type:'service_request',portal_visible:true,default_for_type:false,requester_layout:[],technician_layout:[],lifecycle_state:'draft',version:1,archived_at:null})
const makeField=(type:string,values:Partial<Field>={}):Field=>{
  const definition=fieldTypes.find(item=>item.type===type)!
  const label=values.label||definition.label
  return {id:id(),key:type==='section'?'':keyFrom(label)||`field_${Date.now()}`,label,type,required:false,help:'',
    options:['select','choice_cards','radio','multi_select'].includes(type)?['Option 1','Option 2']:[],
    width:definition.defaultWidth,placeholder:'',icon:definition.icon,max_length:['short_text','email','phone'].includes(type)?100:type==='long_text'?4000:null,visibility:'visible',read_only:false,default_value:null,show_when:null,required_when:null,classification:'public',mask_value:false,access_roles:[],retention_days:null,reportable:true,...values}
}
const section=(label:string,help:string,icon:string)=>makeField('section',{label,help,icon,width:'full'})

const serviceRequestFields=():Field[]=>[
  section('Requester information','Tell us who needs help and the best way to reach them.','1'),
  makeField('short_text',{key:'full_name',label:'Full name',required:true,placeholder:'Enter your full name',width:'half'}),
  makeField('email',{key:'email_address',label:'Email address',required:true,placeholder:'name@company.com',width:'half'}),
  makeField('phone',{key:'phone_number',label:'Phone number',required:true,placeholder:'(555) 123-4567',width:'half'}),
  makeField('short_text',{key:'employee_id',label:'Employee ID',placeholder:'Enter your employee ID',width:'half'}),
  makeField('select',{key:'department',label:'Department',required:true,options:['Information Technology','Operations','Finance','Human Resources','Sales','Marketing','Other'],width:'half'}),
  makeField('select',{key:'location',label:'Location / site',required:true,options:['Headquarters','Remote','Branch office','Client site','Other'],width:'half'}),
  makeField('user',{key:'manager',label:'Manager / supervisor',help:'Optional',width:'half'}),
  makeField('select',{key:'preferred_contact',label:'Preferred contact method',required:true,options:['Email','Phone','Microsoft Teams'],width:'half'}),
  section('Request type','Choose the service area that best matches what you need.','2'),
  makeField('choice_cards',{key:'request_category',label:'Request category',required:true,options:['Hardware','Software / application','Access / account','Network / internet','Email / Microsoft 365','Printing','Other'],width:'full'}),
  makeField('section',{label:'Hardware details',help:'Questions shown only for hardware requests.',icon:'H',show_when:{key:'request_category',value:'Hardware'}}),
  makeField('select',{key:'hardware_type',label:'Hardware type',options:['Laptop','Desktop','Monitor','Docking station','Phone','Peripheral','Other'],required:true,width:'half',show_when:{key:'request_category',value:'Hardware'}}),
  makeField('radio',{key:'device_powers_on',label:'Does the device power on?',options:['Yes','No','Intermittently'],required:true,width:'half',show_when:{key:'request_category',value:'Hardware'}}),
  makeField('checkbox',{key:'physical_damage',label:'The device has visible physical damage.',width:'full',show_when:{key:'request_category',value:'Hardware'}}),
  makeField('section',{label:'Software / application details',help:'Questions shown only for application requests.',icon:'S',show_when:{key:'request_category',value:'Software / application'}}),
  makeField('short_text',{key:'application_name',label:'Application',required:true,width:'half',show_when:{key:'request_category',value:'Software / application'}}),
  makeField('short_text',{key:'application_version',label:'Application version',width:'half',show_when:{key:'request_category',value:'Software / application'}}),
  makeField('radio',{key:'software_problem',label:'What do you need?',options:['Fix a problem','Install application','Access / login','Application unavailable'],required:true,width:'full',show_when:{key:'request_category',value:'Software / application'}}),
  makeField('section',{label:'Access and permissions',help:'Questions shown only for access requests.',icon:'A',show_when:{key:'request_category',value:'Access / account'}}),
  makeField('short_text',{key:'access_system',label:'Application or system',required:true,width:'half',show_when:{key:'request_category',value:'Access / account'}}),
  makeField('select',{key:'access_action',label:'Access change',options:['New access','Modify access','Remove access'],required:true,width:'half',show_when:{key:'request_category',value:'Access / account'}}),
  makeField('long_text',{key:'access_justification',label:'Business justification',required:true,width:'full',show_when:{key:'request_category',value:'Access / account'}}),
  section('Request details','Give the service desk enough context to resolve this without unnecessary back-and-forth.','3'),
  makeField('select',{key:'request_type',label:'Request type',required:true,options:['Incident / issue','Service request','Question / guidance','Security concern'],width:'third'}),
  makeField('select',{key:'category',label:'Category',required:true,options:['Computer','Application','Account','Connectivity','Mobile device','Peripheral','Other'],width:'third'}),
  makeField('select',{key:'subcategory',label:'Subcategory',required:true,options:['Not working','Performance issue','New setup','Change needed','Access required','Other'],width:'third'}),
  makeField('asset',{key:'affected_asset',label:'Item / service affected',help:'Select the affected company asset when applicable.',width:'half'}),
  makeField('select',{key:'recurring',label:'Is this issue recurring?',options:['No — first occurrence','Yes — occasionally','Yes — frequently'],width:'half'}),
  makeField('long_text',{key:'detailed_description',label:'Detailed description',required:true,placeholder:'Describe what happened, what you expected, and anything that changed recently.',width:'full'}),
  makeField('long_text',{key:'troubleshooting',label:'Troubleshooting already attempted',placeholder:'List any steps you already tried and what happened.',width:'half'}),
  makeField('long_text',{key:'error_messages',label:'Error messages or additional context',placeholder:'Paste the exact error or add any other useful context.',width:'half'}),
  section('Impact and priority','Help us understand the business effect and how quickly assistance is needed.','4'),
  makeField('radio',{key:'impact',label:'Impact',required:true,options:['Low','Medium','High'],help:'How broadly does this affect work?',width:'third'}),
  makeField('radio',{key:'urgency',label:'Urgency',required:true,options:['Low','Medium','High'],help:'How quickly is a resolution needed?',width:'third'}),
  makeField('select',{key:'affected_users',label:'People affected',required:true,options:['Only me','My team','A department','Multiple departments','Company-wide'],width:'third'}),
  makeField('long_text',{key:'business_impact',label:'Business impact',placeholder:'Explain blocked work, deadlines, customer impact, or financial risk.',width:'full'}),
  section('Availability and follow-up','Tell the technician when and how they can work with you.','5'),
  makeField('select',{key:'best_time',label:'Best time to contact',options:['Anytime','Morning','Afternoon','After hours'],width:'half'}),
  makeField('phone',{key:'alternate_contact',label:'Alternate contact',placeholder:'Optional phone number',width:'half'}),
  makeField('checkbox',{key:'permission_to_contact',label:'The service desk may contact me for additional information.',required:true,width:'full'}),
  section('Attachments','Add screenshots, documents, logs, or other evidence that can help the service desk.','6'),
  makeField('attachment',{key:'attachments',label:'Supporting files',help:'Up to 10 files, 25 MB each.',width:'full'}),
]

const templates:{name:string;description:string;icon:string;category:string;fields:()=>Field[]}[]=[
  {name:'Complete IT service request',description:'A comprehensive, best-practice service desk intake form.',icon:'✦',category:'IT Support',fields:serviceRequestFields},
  {name:'Incident report',description:'Capture symptoms, impact, urgency, evidence, and troubleshooting.',icon:'!',category:'Incident',fields:()=>serviceRequestFields().filter(field=>!['manager','employee_id','alternate_contact'].includes(field.key))},
  {name:'Access request',description:'Request accounts, permissions, applications, or shared resources.',icon:'◇',category:'Access',fields:()=>[
    section('Requester','Who needs access?','1'),makeField('user',{key:'requested_for',label:'Access requested for',required:true}),
    makeField('user',{key:'manager',label:'Manager / approver',required:true}),section('Access details','Describe the system and access level needed.','2'),
    makeField('choice_cards',{key:'access_type',label:'Access type',required:true,options:['New account','Add permission','Remove permission','Shared mailbox','Application role']}),
    makeField('short_text',{key:'system_name',label:'System or application',required:true,width:'half'}),
    makeField('select',{key:'duration',label:'Duration',required:true,options:['Permanent','Temporary — 1 day','Temporary — 1 week','Temporary — 30 days'],width:'half'}),
    makeField('long_text',{key:'business_reason',label:'Business justification',required:true}),
  ]},
  {name:'Change management',description:'Plan, assess, approve, schedule, and review controlled changes.',icon:'↻',category:'Change',fields:()=>[
    section('Change overview','Define the outcome and ownership of the proposed change.','1'),
    makeField('select',{key:'change_type',label:'Change type',required:true,options:['Standard','Normal','Emergency'],width:'third'}),
    makeField('user',{key:'change_owner',label:'Change owner',required:true,width:'third'}),
    makeField('select',{key:'environment',label:'Environment',required:true,options:['Production','Test','Development','Multiple'],width:'third'}),
    makeField('long_text',{key:'business_reason',label:'Business reason and expected outcome',required:true}),
    section('Risk and implementation','Explain how the change will be delivered safely.','2'),
    makeField('radio',{key:'impact',label:'Impact',required:true,options:['Low','Medium','High'],width:'third'}),
    makeField('radio',{key:'urgency',label:'Urgency',required:true,options:['Low','Medium','High'],width:'third'}),
    makeField('radio',{key:'risk',label:'Risk',required:true,options:['Low','Medium','High'],width:'third'}),
    makeField('long_text',{key:'implementation_plan',label:'Implementation plan',required:true,width:'half'}),
    makeField('long_text',{key:'rollback_plan',label:'Rollback plan',required:true,width:'half'}),
    makeField('long_text',{key:'test_plan',label:'Validation and test plan',required:true,width:'half'}),
    makeField('long_text',{key:'communication_plan',label:'Communication plan',required:true,width:'half'}),
    section('Schedule','Define the implementation window.','3'),
    makeField('date',{key:'planned_date',label:'Planned date',required:true,width:'half'}),
    makeField('time',{key:'planned_time',label:'Planned start time',required:true,width:'half'}),
  ]},
]

function iconFor(type:string){return fieldTypes.find(item=>item.type===type)?.icon||'T'}
function formIcon(value:string){
  const icons:Record<string,string>={form:'✦',support:'⌁',incident:'!',change:'↻',access:'◇',request:'+'}
  return icons[(value||'').toLowerCase()]||(/^[a-z]{3,}$/i.test(value||'')?'✦':value)||'✦'
}

export function VisualFormStudio({forms,saved,testData}:{forms:FormDef[];saved:(text:string)=>void;testData?:any}){
  const [draft,setDraft]=useState<FormDef>(blankForm())
  const [selectedId,setSelectedId]=useState<string|null>(null)
  const [dragIndex,setDragIndex]=useState<number|null>(null)
  const [mode,setMode]=useState<'build'|'preview'>('build')
  const [canvasSize,setCanvasSize]=useState<'desktop'|'tablet'|'mobile'>('desktop')
  const [audience,setAudience]=useState<'requester'|'technician'>('requester')
  const [query,setQuery]=useState('')
  const [error,setError]=useState('')
  const [saving,setSaving]=useState(false)
  const [testValues,setTestValues]=useState<Record<string,any>>({})
  const [testResult,setTestResult]=useState<{kind:'success'|'error';text:string}|null>(null)
  const [versions,setVersions]=useState<any[]|null>(null)
  const selected=useMemo(()=>draft.fields.find(field=>field.id===selectedId)||null,[draft.fields,selectedId])
  const groups=useMemo(()=>Array.from(new Set(fieldTypes.map(item=>item.group))),[])
  const savedForms=useMemo(()=>forms.filter(form=>!form.is_template).sort((a,b)=>Number(a.published)-Number(b.published)||a.name.localeCompare(b.name)),[forms])
  const customTemplates=useMemo(()=>forms.filter(form=>form.is_template),[forms])

  const layoutKey=audience==='requester'?'requester_layout':'technician_layout'
  const orderedFields=useMemo(()=>{const order=draft[layoutKey]||[];const byId=new Map(draft.fields.map(field=>[field.id,field]));return [...order.map(item=>byId.get(item)).filter(Boolean) as Field[],...draft.fields.filter(field=>!order.includes(field.id))]},[draft,layoutKey])
  function choose(form?:FormDef){const next=form?JSON.parse(JSON.stringify(form)):blankForm();const ids=next.fields.map((field:Field)=>field.id);next.requester_layout=next.requester_layout?.length?next.requester_layout:ids;next.technician_layout=next.technician_layout?.length?next.technician_layout:ids;setDraft(next);setSelectedId(null);setError('');setMode('build');setAudience('requester');setTestValues({});setTestResult(null);setVersions(null)}
  function insert(type:string,index=orderedFields.length){const field=makeField(type);const fields=[...draft.fields,field];const requester=[...(draft.requester_layout||draft.fields.map(item=>item.id))];const technician=[...(draft.technician_layout||draft.fields.map(item=>item.id))];const active=audience==='requester'?requester:technician;active.splice(index,0,field.id);const other=audience==='requester'?technician:requester;other.push(field.id);setDraft({...draft,fields,requester_layout:audience==='requester'?active:other,technician_layout:audience==='technician'?active:other});setSelectedId(field.id)}
  function drop(e:DragEvent,index:number){e.preventDefault();const type=e.dataTransfer.getData('field-type');if(type){insert(type,index);return}if(dragIndex===null)return;const order=orderedFields.map(field=>field.id);const [moved]=order.splice(dragIndex,1);const target=dragIndex<index?index-1:index;order.splice(target,0,moved);setDraft({...draft,[layoutKey]:order});setDragIndex(null)}
  function updateField(next:Field){setDraft({...draft,fields:draft.fields.map(field=>field.id===next.id?next:field)})}
  function removeField(fieldId:string){setDraft({...draft,fields:draft.fields.filter(field=>field.id!==fieldId),requester_layout:(draft.requester_layout||[]).filter(id=>id!==fieldId),technician_layout:(draft.technician_layout||[]).filter(id=>id!==fieldId)});setSelectedId(null)}
  function duplicateField(field:Field){const copy={...field,id:id(),key:field.type==='section'?'':`${field.key}_copy`,label:`${field.label} copy`};const fields=[...draft.fields,copy];const requester=[...(draft.requester_layout||draft.fields.map(item=>item.id)),copy.id];const technician=[...(draft.technician_layout||draft.fields.map(item=>item.id)),copy.id];setDraft({...draft,fields,requester_layout:requester,technician_layout:technician});setSelectedId(copy.id)}
  function useTemplate(template:typeof templates[number]){const fields=template.fields();setDraft({...blankForm(),name:template.name,slug:slug(template.name),description:template.description,category:template.category,icon:template.icon,fields});setSelectedId(fields[0]?.id||null);setTestValues({});setTestResult(null)}
  function useSavedTemplate(template:FormDef){const fields=JSON.parse(JSON.stringify(template.fields));const name=template.name.replace(/\s+template$/i,'');setDraft({...blankForm(),name,slug:slug(name),description:template.description,category:template.category,icon:template.icon,fields});setSelectedId(fields[0]?.id||null);setTestValues({});setTestResult(null)}
  function visibleToAudience(field:Field){return field.visibility!=='hidden'&&(audience==='technician'||field.visibility!=='technician_only')}
  function validateTest(){
    const missing=orderedFields.filter(field=>field.type!=='section'&&visibleToAudience(field)&&(!field.show_when||String(testValues[field.show_when.key]||'')===field.show_when.value)&&(field.required||(field.required_when&&String(testValues[field.required_when.key]||'')===field.required_when.value))&&(Array.isArray(testValues[field.key])?!testValues[field.key].length:!testValues[field.key]&&field.default_value==null)).map(field=>field.label)
    const invalidEmail=draft.fields.find(field=>field.type==='email'&&testValues[field.key]&&!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(String(testValues[field.key])))
    if(missing.length){setTestResult({kind:'error',text:`Complete required field${missing.length===1?'':'s'}: ${missing.join(', ')}.`});return}
    if(invalidEmail){setTestResult({kind:'error',text:`Enter a valid email address in ${invalidEmail.label}.`});return}
    setTestResult({kind:'success',text:'Live test passed. Every required field has an accepted value. No ticket was created.'})
  }
  async function save(kind:'draft'|'template'|'publish'){
    setError('');setSaving(true)
    try{
      const asTemplate=kind==='template'
      const payload={...draft,published:kind==='publish',is_template:asTemplate}
      const path=asTemplate?'/admin/forms':draft.id?`/admin/forms/${draft.id}`:'/admin/forms'
      const method=asTemplate?'POST':draft.id?'PATCH':'POST'
      if(asTemplate){delete payload.id;payload.name=`${draft.name} template`;payload.slug=`${draft.slug}-template-${Date.now()}`}
      await api(path,{method,body:JSON.stringify(payload)})
      await saved(asTemplate?`${draft.name} saved as a reusable template.`:kind==='publish'?`${draft.name} published to the service catalog.`:`${draft.name} saved as a draft and remains hidden from the service catalog.`)
      choose()
    }catch(e:any){setError(e.message)}finally{setSaving(false)}
  }
  async function copyCurrent(){if(!draft.id)return;try{await api(`/admin/forms/${draft.id}/copy`,{method:'POST'});await saved(`${draft.name} copied as a new draft.`);choose()}catch(e:any){setError(e.message)}}
  async function archiveCurrent(){if(!draft.id||!confirm(`Archive ${draft.name}? It will be removed from the service catalog.`))return;try{await api(`/admin/forms/${draft.id}`,{method:'DELETE'});await saved(`${draft.name} archived.`);choose()}catch(e:any){setError(e.message)}}
  async function unarchiveCurrent(){if(!draft.id)return;try{await api(`/admin/forms/${draft.id}/unarchive`,{method:'POST'});await saved(`${draft.name} restored as a private draft.`);choose()}catch(e:any){setError(e.message)}}
  async function loadVersions(){if(!draft.id)return;try{setVersions(await api(`/admin/forms/${draft.id}/versions`))}catch(e:any){setError(e.message)}}
  async function restoreVersion(version:any){if(!draft.id||!confirm(`Restore version ${version.version} as a new draft revision?`))return;try{await api(`/admin/forms/${draft.id}/versions/${version.id}/restore`,{method:'POST'});await saved(`Version ${version.version} restored.`);choose()}catch(e:any){setError(e.message)}}

  return <div className="vs-shell">
    <header className="vs-toolbar">
      <div><span className="vs-mark">✦</span><div><strong>Form Studio</strong><small>{draft.id?`Editing · ${draft.published?'Published':'Draft'}`:'Create a service experience'}</small></div></div>
      <div className="vs-mode" aria-label="Design mode"><button className={mode==='build'?'active':''} onClick={()=>setMode('build')}>Build</button><button className={mode==='preview'?'active':''} onClick={()=>{setMode('preview');setSelectedId(null);setTestResult(null)}}>Live test</button></div>
      <div className="vs-actions"><button className="vs-secondary" onClick={()=>choose()}>New</button><button className="vs-secondary" disabled={saving||!draft.name||!draft.slug||!draft.fields.length} onClick={()=>save('template')}>Save template</button><button className="vs-secondary" disabled={saving||!draft.name||!draft.slug||!draft.fields.length} onClick={()=>save('draft')}>Save draft</button><button className="primary" disabled={saving||!draft.name||!draft.slug||!draft.fields.length} onClick={()=>save('publish')}>{saving?'Saving…':'Publish'}</button></div>
    </header>
    {error&&<div className="alert danger">{error}</div>}
    <div className={`vs-workspace ${mode==='preview'?'previewing':''}`}>
      {mode==='build'&&<aside className="vs-left-panel">
        <div className="vs-panel-title"><div><span>FORM LIBRARY</span><strong>Saved forms</strong></div><button onClick={()=>choose()}>+</button></div>
        <div className="vs-form-list">{savedForms.map(form=><button className={`${draft.id===form.id?'active ':''}${form.slug==='studio-field-test'?'test-form':''}`} onClick={()=>choose(form)} key={form.id}><i>{formIcon(form.icon)}</i><span><strong>{form.name}{form.slug==='studio-field-test'&&<em>TEST</em>}</strong><small>{form.fields.filter(field=>field.type!=='section').length} fields · {form.published?'Live':'Draft — hidden from catalog'}</small></span></button>)}</div>
        <div className="vs-elements-head"><span>ELEMENTS</span><input value={query} onChange={e=>setQuery(e.target.value)} placeholder="Search fields…"/></div>
        <div className="vs-element-library">{groups.map(group=>{const types=fieldTypes.filter(item=>item.group===group&&`${item.label} ${item.help}`.toLowerCase().includes(query.toLowerCase()));return types.length?<section key={group}><h4>{group}</h4><div>{types.map(item=><button draggable title={`${item.label}: ${item.help}`} aria-label={`${item.label}. ${item.help}`} onDragStart={e=>e.dataTransfer.setData('field-type',item.type)} onClick={()=>insert(item.type)} key={item.type}><i>{item.icon}</i><span>{item.label}</span><b className="vs-help-dot">?</b></button>)}</div></section>:null})}</div>
      </aside>}
      <main className="vs-stage">
        <div className="vs-role-tools"><strong>Design and preview as</strong><button className={audience==='requester'?'active':''} onClick={()=>setAudience('requester')}>Requester</button><button className={audience==='technician'?'active':''} onClick={()=>setAudience('technician')}>Technician</button><small>Each view keeps its own field order.</small></div>
        <div className="vs-stage-tools"><span>{mode==='build'?'Click a field to configure it. Drag to reorder.':'Live test mode — enter answers and validate the form. Nothing is submitted.'}</span><div>{(['desktop','tablet','mobile'] as const).map(size=><button className={canvasSize===size?'active':''} onClick={()=>setCanvasSize(size)} key={size} title={size}>{size==='desktop'?'▰':size==='tablet'?'▯':'▯'}</button>)}</div></div>
        <div className={`vs-canvas-wrap ${canvasSize}`}>
          <article className="vs-form-canvas" onDragOver={e=>e.preventDefault()} onDrop={e=>drop(e,draft.fields.length)}>
            <header className="vs-form-header"><div className="vs-form-icon">{formIcon(draft.icon)}</div><div className="vs-form-heading"><p>{draft.category||'IT SERVICE DESK'}</p><h2>{draft.name||'Untitled service request'}</h2><span>{draft.description||'Add a short introduction so people know when and how to use this form.'}</span></div><div className="vs-service-promise"><b>Service Desk</b><span>Secure submission</span><small>We’ll keep you updated</small></div></header>
            {!draft.fields.length?<div className="vs-empty-canvas"><span>＋</span><h3>Start with a professional template</h3><p>Choose a starter on the right, or drag fields from the library.</p></div>:<div className="vs-fields-grid">
              {orderedFields.filter(field=>mode==='build'||(visibleToAudience(field)&&(!field.show_when||String(testValues[field.show_when.key]||'')===field.show_when.value))).map((field,index)=><FieldCanvas field={field} index={index} selected={selectedId===field.id} preview={mode==='preview'} value={testValues[field.key]??field.default_value} setValue={value=>{setTestValues({...testValues,[field.key]:value});setTestResult(null)}} testData={testData} onSelect={()=>setSelectedId(field.id)} onDragStart={()=>setDragIndex(index)} onDrop={e=>{e.stopPropagation();drop(e,index)}} key={field.id}/>)}
            </div>}
            {mode==='preview'&&testResult&&<div className={`vs-test-result ${testResult.kind}`}>{testResult.text}</div>}
            {!!draft.fields.length&&<footer className="vs-form-footer"><span>{mode==='preview'?'◉ Live test only — no ticket will be created.':'▣ Your request will be sent securely to the IT Service Desk.'}</span><div>{mode==='preview'?<><button onClick={()=>{setTestValues({});setTestResult(null)}}>Clear answers</button><button className="primary" onClick={validateTest}>Validate test form ✓</button></>:<><button>Save draft</button><button className="primary">Submit request →</button></>}</div></footer>}
          </article>
        </div>
      </main>
      {mode==='build'&&<aside className="vs-inspector">
        {selected?<FieldInspector field={selected} allFields={draft.fields} update={updateField} remove={()=>removeField(selected.id)} duplicate={()=>duplicateField(selected)}/>:<FormInspector draft={draft} update={setDraft} useTemplate={useTemplate} customTemplates={customTemplates} useSavedTemplate={useSavedTemplate} copyCurrent={copyCurrent} archiveCurrent={archiveCurrent} unarchiveCurrent={unarchiveCurrent} loadVersions={loadVersions} versions={versions} restoreVersion={restoreVersion}/>} 
      </aside>}
    </div>
  </div>
}

function FieldCanvas({field,index,selected,preview,value,setValue,testData,onSelect,onDragStart,onDrop}:{field:Field;index:number;selected:boolean;preview:boolean;value:any;setValue:(value:any)=>void;testData?:any;onSelect:()=>void;onDragStart:()=>void;onDrop:(e:DragEvent)=>void}){
  if(field.type==='section')return <section className={`vs-section-block ${selected?'selected':''}`} draggable={!preview} onDragStart={onDragStart} onDragOver={e=>e.preventDefault()} onDrop={onDrop} onClick={preview?undefined:onSelect}><span>{field.icon||index+1}</span><div><h3>{field.label}</h3><p>{field.help}</p></div>{!preview&&<b>⋮⋮</b>}</section>
  return <div className={`vs-preview-field width-${field.width||'full'} ${selected?'selected':''} ${preview?'testing':''}`} draggable={!preview} onDragStart={onDragStart} onDragOver={e=>e.preventDefault()} onDrop={onDrop} onClick={preview?undefined:onSelect}>
    {!preview&&<span className="vs-field-drag">⋮⋮</span>}<label>{field.label}{field.required&&<b> *</b>}</label><PreviewControl field={field} interactive={preview} value={value} setValue={setValue} testData={testData}/>{field.help&&<small>{field.help}</small>}
  </div>
}

function PreviewControl({field,interactive,value,setValue,testData}:{field:Field;interactive:boolean;value:any;setValue:(value:any)=>void;testData?:any}){
  if(interactive){
    if(field.type==='long_text')return <div className="vs-live-text"><textarea className="vs-live-control" rows={4} required={field.required} maxLength={field.max_length||undefined} value={value||''} onChange={e=>setValue(e.target.value)} placeholder={field.placeholder||'Enter a detailed response…'}/>{field.max_length&&<small>{String(value||'').length} / {field.max_length}</small>}</div>
    if(field.type==='choice_cards')return <div className="vs-choice-preview interactive">{field.options.map((option,index)=><button type="button" className={value===option?'selected':''} onClick={()=>setValue(option)} key={option}><i>{['▰','◈','♙','⌁','@','▤','⚙'][index%7]}</i>{option}</button>)}</div>
    if(field.type==='radio')return <div className="vs-radio-preview interactive">{field.options.map(option=><label key={option}><input type="radio" name={`test-${field.id}`} checked={value===option} onChange={()=>setValue(option)}/>{option}</label>)}</div>
    if(field.type==='checkbox')return <label className="vs-checkbox-preview interactive"><input type="checkbox" checked={!!value} onChange={e=>setValue(e.target.checked)}/>{field.help||'Select to confirm'}</label>
    if(field.type==='select')return <select className="vs-live-control" value={value||''} onChange={e=>setValue(e.target.value)}><option value="">{field.placeholder||'Choose…'}</option>{field.options.map(option=><option key={option}>{option}</option>)}</select>
    if(field.type==='multi_select')return <select className="vs-live-control" multiple value={value||[]} onChange={e=>setValue(Array.from(e.target.selectedOptions).map(option=>option.value))}>{field.options.map(option=><option key={option}>{option}</option>)}</select>
	    if(field.type==='asset')return <select className="vs-live-control" value={value||''} onChange={e=>setValue(e.target.value)}><option value="">{field.placeholder||'Choose an asset…'}</option>{(testData?.assets||[]).map((asset:any)=><option value={asset.id} key={asset.id}>{asset.asset_tag} · {asset.hostname||asset.model||'Asset'} · {asset.asset_type||'Device'}</option>)}</select>
	    if(field.type==='attachment')return <input className="vs-live-control" type="file" multiple onChange={e=>setValue(Array.from(e.target.files||[]).map(file=>file.name))}/>
    if(field.type==='user')return <select className="vs-live-control" value={value||''} onChange={e=>setValue(e.target.value)}><option value="">{field.placeholder||'Choose a person…'}</option>{(testData?.requesters||[]).map((person:any)=><option value={person.id} key={person.id}>{person.display_name} · {person.email}</option>)}</select>
    const inputType=field.type==='date'?'date':field.type==='time'?'time':field.type==='number'?'number':field.type==='email'?'email':field.type==='phone'?'tel':'text'
    return <input className="vs-live-control" type={inputType} required={field.required} maxLength={field.max_length||undefined} size={field.max_length?Math.min(field.max_length,60):undefined} style={field.max_length?{maxWidth:`min(100%, ${Math.max(8,field.max_length+3)}ch)`}:undefined} value={value||''} onChange={e=>setValue(e.target.value)} placeholder={field.placeholder||`Enter ${field.label.toLowerCase()}`}/>
  }
  if(field.type==='long_text')return <div className="vs-fake-control textarea">{field.placeholder||'Enter a detailed response…'}</div>
  if(field.type==='choice_cards')return <div className="vs-choice-preview">{field.options.map((option,index)=><span className={index===0?'selected':''} key={option}><i>{['▰','◈','♙','⌁','@','▤','⚙'][index%7]}</i>{option}</span>)}</div>
  if(field.type==='radio')return <div className="vs-radio-preview">{field.options.map(option=><span key={option}><i/> {option}</span>)}</div>
	  if(field.type==='checkbox')return <div className="vs-checkbox-preview"><i/> {field.help||'Select to confirm'}</div>
	  if(field.type==='attachment')return <div className="vs-fake-control">Drag files here or click to browse <b>↥</b></div>
  if(field.type==='select'||field.type==='multi_select'||field.type==='asset'||field.type==='user')return <div className="vs-fake-control">{field.placeholder||`Select ${field.label.toLowerCase()}`}<b>⌄</b></div>
  return <div className="vs-fake-control">{field.placeholder||`Enter ${field.label.toLowerCase()}`}</div>
}

function FormInspector({draft,update,useTemplate,customTemplates,useSavedTemplate,copyCurrent,archiveCurrent,unarchiveCurrent,loadVersions,versions,restoreVersion}:{draft:FormDef;update:(form:FormDef)=>void;useTemplate:(template:typeof templates[number])=>void;customTemplates:FormDef[];useSavedTemplate:(template:FormDef)=>void;copyCurrent:()=>void;archiveCurrent:()=>void;unarchiveCurrent:()=>void;loadVersions:()=>void;versions:any[]|null;restoreVersion:(version:any)=>void}){
  return <><div className="vs-inspector-head"><span>FORM</span><h3>Form settings</h3><p>Set the identity, publishing status, and starting structure.</p></div>
    <div className="vs-property-form"><label>Form name<input value={draft.name} onChange={e=>update({...draft,name:e.target.value,slug:draft.id?draft.slug:slug(e.target.value)})} placeholder="IT service request"/></label><label>Introduction<textarea value={draft.description} onChange={e=>update({...draft,description:e.target.value})} rows={3}/></label><div className="vs-two"><label>Category<input value={draft.category} onChange={e=>update({...draft,category:e.target.value})}/></label><label>Icon<input value={draft.icon} onChange={e=>update({...draft,icon:e.target.value})}/></label></div><label>Form key<input value={draft.slug} onChange={e=>update({...draft,slug:slug(e.target.value)})}/></label><label>Request type<select value={draft.form_type||'service_request'} onChange={e=>update({...draft,form_type:e.target.value})}><option value="service_request">Service request</option><option value="incident">Incident</option><option value="change">Change</option><option value="access_request">Access request</option><option value="problem">Problem</option></select></label><label className="vs-switch"><input type="checkbox" checked={draft.portal_visible!==false} onChange={e=>update({...draft,portal_visible:e.target.checked})}/><span><b>Visible in requester portal</b><small>Published forms can still be kept technician-only.</small></span></label><label className="vs-switch"><input type="checkbox" checked={!!draft.default_for_type} onChange={e=>update({...draft,default_for_type:e.target.checked})}/><span><b>Default for this request type</b><small>Replaces the previous default when saved.</small></span></label><label className="vs-switch"><input type="checkbox" checked={draft.active} onChange={e=>update({...draft,active:e.target.checked})}/><span><b>Active</b><small>Inactive forms cannot be submitted.</small></span></label><div className={`vs-publish-status ${draft.published?'live':'draft'}`}><b>{draft.archived_at?'Archived':draft.published?'Published':'Draft'}</b><small>{draft.archived_at?'Restore this form before editing or publishing it.':draft.published?'This form is available in the service catalog. Save draft to hide it again.':'This form is private to Studio. It will appear in the service catalog only after you click Publish.'}</small></div>{draft.id&&<div className="vs-form-admin-actions"><button type="button" onClick={copyCurrent}>Copy</button><button type="button" onClick={loadVersions}>Version history</button>{draft.archived_at?<button type="button" onClick={unarchiveCurrent}>Restore archived form</button>:<button type="button" className="danger" onClick={archiveCurrent}>Archive</button>}</div>}{versions&&<div className="vs-version-list"><strong>Change history</strong>{versions.map(version=><article key={version.id}><span><b>Version {version.version}</b><small>{new Date(version.created_at).toLocaleString()}</small></span><button type="button" onClick={()=>restoreVersion(version)}>Restore</button></article>)}</div>}</div>
    {!draft.fields.length&&<div className="vs-template-list"><div><span>STARTER KITS</span><h3>Build from a proven pattern</h3></div>{templates.map(template=><button onClick={()=>useTemplate(template)} key={template.name}><i>{template.icon}</i><span><strong>{template.name}</strong><small>{template.description}</small></span><b>→</b></button>)}{!!customTemplates.length&&<div className="vs-custom-template-heading"><span>SAVED TEMPLATES</span><h3>Your reusable patterns</h3></div>}{customTemplates.map(template=><button onClick={()=>useSavedTemplate(template)} key={template.id}><i>{formIcon(template.icon)}</i><span><strong>{template.name.replace(/\s+template$/i,'')}</strong><small>{template.description||'Create a new draft from this saved template.'}</small></span><b>→</b></button>)}</div>}
  </>
}

function FieldInspector({field,allFields,update,remove,duplicate}:{field:Field;allFields:Field[];update:(field:Field)=>void;remove:()=>void;duplicate:()=>void}){
  const choice=['select','choice_cards','radio','multi_select'].includes(field.type)
  return <><div className="vs-inspector-head"><span>FIELD</span><h3>{field.label}</h3><p>Configure content, validation, and layout.</p></div><div className="vs-property-form">
    <label>Label<input value={field.label} onChange={e=>update({...field,label:e.target.value})}/></label>
    {field.type!=='section'&&<label>Data key<input value={field.key} onChange={e=>update({...field,key:keyFrom(e.target.value)})}/><small>Used in reports and automations</small></label>}
    <label>Field type<select value={field.type} onChange={e=>{const next=makeField(e.target.value,{...field,type:e.target.value});update(next)}}>{fieldTypes.map(item=><option value={item.type} key={item.type}>{item.label}</option>)}</select></label>
    {field.type!=='section'&&<label>Placeholder<input value={field.placeholder||''} onChange={e=>update({...field,placeholder:e.target.value})} placeholder="Helpful example or instruction"/></label>}
    {['short_text','long_text','email','phone'].includes(field.type)&&<label>Character limit<input type="number" min="1" max={field.type==='long_text'?20000:500} value={field.max_length||''} onChange={e=>update({...field,max_length:e.target.value?Math.max(1,+e.target.value):null})} placeholder={field.type==='long_text'?'4000':'100'}/><small>Controls both the maximum answer length and the visible input size. Example: 8 for an employee code or 25 for a short name.</small></label>}
    <label>{field.type==='section'?'Section guidance':'Help text'}<textarea value={field.help} onChange={e=>update({...field,help:e.target.value})} rows={3}/></label>
    <label>Visibility<select value={field.visibility||'visible'} onChange={e=>update({...field,visibility:e.target.value as Field['visibility']})}><option value="visible">Requester and technician</option><option value="technician_only">Technician only</option><option value="hidden">Hidden from both views</option></select><small>Technician-only fields provide internal context without appearing on the requester form.</small></label>
    {field.type!=='section'&&field.type!=='attachment'&&<label>Default value<input value={Array.isArray(field.default_value)?field.default_value.join(', '):(field.default_value??'')} onChange={e=>update({...field,default_value:e.target.value||null})} placeholder="Optional pre-filled value"/><small>Read-only fields should normally have a default value.</small></label>}
    <label>Show only when<select value={field.show_when?.key||''} onChange={e=>update({...field,show_when:e.target.value?{key:e.target.value,value:field.show_when?.value||''}:null})}><option value="">Always show</option>{allFields.filter(item=>item.id!==field.id&&item.type!=='section').map(item=><option value={item.key} key={item.id}>{item.label}</option>)}</select>{field.show_when&&<input value={field.show_when.value} onChange={e=>update({...field,show_when:{...field.show_when!,value:e.target.value}})} placeholder="Required answer, exactly as configured"/>}<small>Use this to show request-type-specific questions only after a matching answer.</small></label>
    {field.type!=='section'&&<label>Required only when<select value={field.required_when?.key||''} onChange={e=>update({...field,required_when:e.target.value?{key:e.target.value,value:field.required_when?.value||''}:null})}><option value="">Never conditionally required</option>{allFields.filter(item=>item.id!==field.id&&item.type!=='section').map(item=><option value={item.key} key={item.id}>{item.label}</option>)}</select>{field.required_when&&<input value={field.required_when.value} onChange={e=>update({...field,required_when:{...field.required_when!,value:e.target.value}})} placeholder="Answer that makes this required"/>}<small>This is evaluated in addition to the always-required switch.</small></label>}
    {choice&&<OptionEditor field={field} update={update}/>} 
    <label>Width<div className="vs-width-picker">{(['third','half','two_thirds','full'] as const).map(width=><button className={(field.width||'full')===width?'active':''} onClick={()=>update({...field,width})} key={width}><i className={width}/><span>{width.replace('_',' ')}</span></button>)}</div></label>
    {field.type!=='section'&&<label className="vs-switch"><input type="checkbox" checked={field.required} onChange={e=>update({...field,required:e.target.checked})}/><span><b>Required field</b><small>Submission is blocked until completed</small></span></label>}
    {field.type!=='section'&&<label className="vs-switch"><input type="checkbox" checked={!!field.read_only} onChange={e=>update({...field,read_only:e.target.checked})}/><span><b>Read-only</b><small>Show the value without allowing requester changes</small></span></label>}
    {field.type!=='section'&&<><label>Data classification<select value={field.classification||'public'} onChange={e=>update({...field,classification:e.target.value as Field['classification']})}><option value="public">Public to requester</option><option value="internal">Internal service desk</option><option value="restricted">Restricted managers and auditors</option></select></label><label>Allowed roles<input value={(field.access_roles||[]).join(', ')} onChange={e=>update({...field,access_roles:e.target.value.split(',').map(value=>value.trim()).filter(Boolean)})} placeholder="Optional: manager, admin, auditor"/><small>Leave empty to use the classification default.</small></label><label>Retention (days)<input type="number" min="1" max="3650" value={field.retention_days||''} onChange={e=>update({...field,retention_days:e.target.value?+e.target.value:null})} placeholder="Use organization default"/></label><label className="vs-switch"><input type="checkbox" checked={!!field.mask_value} onChange={e=>update({...field,mask_value:e.target.checked})}/><span><b>Mask displayed value</b><small>Only the last four characters remain visible.</small></span></label><label className="vs-switch"><input type="checkbox" checked={field.reportable!==false} onChange={e=>update({...field,reportable:e.target.checked})}/><span><b>Available in reports</b><small>Disable for secrets and regulated data.</small></span></label></>}
    <div className="vs-field-actions"><button onClick={duplicate}>Duplicate</button><button className="danger" onClick={remove}>Delete field</button></div>
  </div></>
}

function OptionEditor({field,update}:{field:Field;update:(field:Field)=>void}){
  function change(index:number,value:string){update({...field,options:field.options.map((option,itemIndex)=>itemIndex===index?value:option)})}
  function add(){update({...field,options:[...field.options,`Option ${field.options.length+1}`]})}
  function remove(index:number){if(field.options.length<=1)return;update({...field,options:field.options.filter((_,itemIndex)=>itemIndex!==index)})}
  return <div className="vs-option-editor">
    <div className="vs-option-title"><span>Options</span><button type="button" onClick={add}>+ Add option</button></div>
    {field.options.map((option,index)=><div className="vs-option-row" key={`${field.id}-${index}`}><span>{index+1}</span><input value={option} onChange={e=>change(index,e.target.value)} placeholder={`Option ${index+1}`}/><button type="button" onClick={()=>remove(index)} disabled={field.options.length<=1} title={field.options.length<=1?'A choice field must keep at least one option.':'Remove this option'} aria-label={`Remove option ${index+1}`}>×</button></div>)}
    <small>Add each answer separately. Requesters will see every row as a selectable choice.</small>
  </div>
}

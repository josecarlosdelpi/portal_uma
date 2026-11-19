import {ApiError, request} from "./api";
export type ReviewRow = {
  store_code:string; count:number|null; tier:"nenhum"|"simbolico"|"maior"|null;
  reward_per_seller:string|null; checked_on:string|null; delivered_on:string|null;
  note:string; revision:number; status:string;
};
export type ReviewSnapshot = {year:number;month:number;source:string;stores:ReviewRow[]};

export type SupplyItem = {
  id:string;name:string;unit:string;balance:number;minimum:number;revision:number;needs_restock:boolean
};
export type SupplySnapshot = {store_code:string;items:SupplyItem[]};
export type SupplyMove = {
  id:string;material_id:string;material:string;store_code:string;kind:"entrada"|"retirada";
  quantity:number;resulting_balance:number;actor:string;note:string;created_at:string
};

export type ClientRow = {
  id:string;store_code:string;name:string;phone:string|null;
  cellphone:string|null;city:string|null;contact_person:string|null;
  birthday:string|null;birthday_day:number|null;birthday_month:number|null;
  status:string|null;tag:string|null;last_contact_on:string|null;
  erp_code:string|null;origin:string;notes:string|null;
  last_purchase_on:string|null;revision:number;
  inactive_by_purchases:boolean|null
};
export type ClientPage = {
  store_code:string;total:number;page:number;page_size:number;items:ClientRow[]
};
export type ClientFilters = {cities:string[];statuses:string[];tags:string[]};
export type ClientDetail = ClientRow & {
  inactivity_days:number;days_since_purchase:number|null;
  history:{items:ContactRow[];total:number;page:number;page_size:number};
  pending_followups:ContactRow[]
};
export type ClientWarning = {code:string;message:string};
export type ClientSaveResult = {
  result:"saved"|"review";client?:ClientRow;warnings:ClientWarning[];revision?:number
};
export type ClientInput = {
  name:string;phone?:string|null;cellphone?:string|null;erp_code?:string|null;
  origin?:string;city?:string|null;contact_person?:string|null;
  birthday_day?:number|null;birthday_month?:number|null;
  status?:string|null;tag?:string|null;last_contact_on?:string|null;
  last_purchase_on?:string|null;notes?:string|null;confirm?:boolean
};
export type TeamMember = {id:string;name:string};
export type ContactRow = {
  id:string;store_code:string;client_id:string;client:string;
  seller_id:string;seller:string;date:string;outcome:string;channel:string;
  next_on:string|null;followup_done_at:string|null;
  note:string;revision:number;overdue?:boolean
};
export type CallsSnapshot = {store_code:string;year:number;month:number;
  total:number;page:number;page_size:number;items:ContactRow[]};
export type FollowupPage = {
  store_code:string;total:number;page:number;page_size:number;items:ContactRow[]
};
export type ContactSettings = {inactivity_days:number};
export type ContactMetrics = {
  store_code:string;year:number;month:number;inactivity_days:number;
  clients_total:number;by_status:Record<string,number>;
  by_city:{city:string;total:number}[];by_tag:{tag:string;total:number}[];
  contacts_in_period:number;clients_contacted:number;
  followups_pending:number;followups_overdue:number;
  inactive_by_purchases:number
};
export type ImportRow = {
  index:number;sheet:string;city:string|null;name:string;
  phone:string|null;cellphone:string|null;contact_person:string|null;
  birthday_day:number|null;birthday_month:number|null;birthday_raw:string|null;
  status:string|null;status_raw:string|null;tag:string|null;
  last_contact_on:string|null;last_contact_raw:string|null;notes:string|null;
  warnings:string[];matches:{id:string;name:string;city:string|null;kinds:string[]}[];
  suggested:"import"|"update"
};
export type ImportPreview = {
  session_id:string;filename:string;rows_total:number;expires_at:string;
  cities:{city:string;total:number}[];rows:ImportRow[];
  summary:{with_warnings:number;possible_duplicates:number}
};
export type ImportReport = {
  imported:number;updated:number;skipped:number;warnings:number
};
export type ImportCommitResult =
  {result:"saved";report:ImportReport;details:{index:number;action:string;client:string}[]}
  | {result:"review";message:string;flagged:number};

export const operationsApi = {
  reviews:(token:string,year:number,month:number) =>
    request<ReviewSnapshot>(token,`/api/v1/operations/reviews/${year}/${month}`),
  saveReview:(token:string,store:string,year:number,month:number,body:{
    count:number;checked_on:string;delivered_on:string|null;note:string;expected_revision:number
  }) => request<ReviewRow>(token,`/api/v1/operations/reviews/${store}/${year}/${month}`,"PUT",body),
  supplies:(token:string,store:string) =>
    request<SupplySnapshot>(token,`/api/v1/operations/supplies/${store}`),
  createMaterial:(token:string,body:{
    name:string;unit:string;minima:Record<string,number>
  }) => request<{id:string;name:string;unit:string}>(token,
    "/api/v1/operations/supplies/materials","POST",body),
  changeMinimum:(token:string,store:string,materialId:string,minimum:number,revision:number) =>
    request<{revision:number}>(token,`/api/v1/operations/supplies/${store}/${materialId}/minimum`,
      "PUT",{minimum,expected_revision:revision}),
  moveSupply:(token:string,body:{
    store_code:string;material_id:string;kind:"entrada"|"retirada";quantity:number;note:string;
    expected_revision:number
  }) => request<{id:string;resulting_balance:number;revision:number}>(token,
    "/api/v1/operations/supplies/movements","POST",body),
  movements:(token:string,store:string) =>
    request<SupplyMove[]>(token,`/api/v1/operations/supplies/${store}/movements`),
  clients:(token:string,store:string,params?:{
    q?:string;city?:string;status?:string;tag?:string;phone?:string;
    inactive?:string;page?:number;page_size?:number
  }) => {
    const query=new URLSearchParams();
    for(const [key,value] of Object.entries(params??{}))
      if(value!==undefined&&value!=="")query.set(key,String(value));
    const suffix=query.size?"?"+query.toString():"";
    return request<ClientPage>(token,
      `/api/v1/operations/contacts/${store}/clients${suffix}`);
  },
  clientFilters:(token:string,store:string) =>
    request<ClientFilters>(token,`/api/v1/operations/contacts/${store}/clients/filters`),
  clientDetail:(token:string,store:string,id:string,
                historyPage:number=1,historySize:number=50) =>
    request<ClientDetail>(token,
      `/api/v1/operations/contacts/${store}/clients/${id}`+
      `?history_page=${historyPage}&history_size=${historySize}`),
  addClient:(token:string,store:string,body:ClientInput) =>
    request<ClientSaveResult>(token,`/api/v1/operations/contacts/${store}/clients`,"POST",body),
  updateClient:(token:string,store:string,id:string,body:Partial<ClientInput>&{
    expected_revision:number
  }) => request<ClientSaveResult>(token,
    `/api/v1/operations/contacts/${store}/clients/${id}`,"PUT",body),
  contactSettings:(token:string,store:string) =>
    request<ContactSettings>(token,`/api/v1/operations/contacts/${store}/settings`),
  saveSettings:(token:string,store:string,inactivityDays:number) =>
    request<ContactSettings>(token,`/api/v1/operations/contacts/${store}/settings`,"PUT",
      {inactivity_days:inactivityDays}),
  contactMetrics:(token:string,store:string,year:number,month:number) =>
    request<ContactMetrics>(token,
      `/api/v1/operations/contacts/${store}/metrics/${year}/${month}`),
  followups:(token:string,store:string,state:string,page=1,pageSize=100) =>
    request<FollowupPage>(token,
      `/api/v1/operations/contacts/${store}/followups?state=${state}&page=${page}&page_size=${pageSize}`),
  followupDone:(token:string,store:string,callId:string,revision:number) =>
    request<ContactRow>(token,
      `/api/v1/operations/contacts/${store}/followups/${callId}/done`,"POST",
      {expected_revision:revision}),
  followupReschedule:(token:string,store:string,callId:string,nextOn:string,revision:number) =>
    request<ContactRow>(token,
      `/api/v1/operations/contacts/${store}/followups/${callId}/reschedule`,"POST",
      {next_on:nextOn,expected_revision:revision}),
  importPreview:(token:string,store:string,file:File,defaultCity?:string) => {
    const form=new FormData();
    form.append("file",file);
    const city=defaultCity?"?default_city="+encodeURIComponent(defaultCity):"";
    return fetch(
      (import.meta.env.VITE_API_BASE_URL??"").replace(/\/$/,"")+
      `/api/v1/operations/contacts/${store}/import/preview${city}`,
      {method:"POST",headers:{Authorization:"Bearer "+token},body:form}
    ).then(async response=>{
      if(!response.ok){
        const detail=await response.json().catch(()=>({}));
        throw new ApiError(response.status,
          (detail as {detail?:string}).detail??"Falha ao ler o arquivo.");
      }
      return response.json() as Promise<ImportPreview>;
    });
  },
  importCommit:(token:string,store:string,sessionId:string,body:{
    decisions:Record<string,{action:"import"|"update"|"skip";client_id?:string}>;
    confirm:boolean
  }) => request<ImportCommitResult>(token,
    `/api/v1/operations/contacts/${store}/import/${sessionId}/commit`,"POST",body),
  team:(token:string,store:string) =>
    request<TeamMember[]>(token,`/api/v1/operations/contacts/${store}/team`),
  calls:(token:string,store:string,year:number,month:number,
         page:number=1,pageSize:number=100) =>
    request<CallsSnapshot>(token,
      `/api/v1/operations/contacts/${store}/${year}/${month}/calls`+
      `?page=${page}&page_size=${pageSize}`),
  discardImport:(token:string,store:string,sessionId:string) =>
    request<{result:string}>(token,
      `/api/v1/operations/contacts/${store}/import/${sessionId}`,"DELETE"),
  exportClients:(token:string,store:string,format:"csv"|"xlsx",params?:{
    q?:string;city?:string;status?:string;tag?:string;phone?:string;
    inactive?:string
  }) => {
    const search=new URLSearchParams();
    if(params)for(const [key,value] of Object.entries(params))
      if(value)search.set(key,value);
    return fetch(
      (import.meta.env.VITE_API_BASE_URL??"").replace(/\/$/,"")+
      `/api/v1/operations/contacts/${store}/export?format=${format}&`+
      search.toString(),
      {headers:{Authorization:"Bearer "+token}}
    ).then(async response=>{
      if(!response.ok){
        const detail=await response.json().catch(()=>({}));
        throw new ApiError(response.status,
          (detail as {detail?:string}).detail??"Falha ao exportar a carteira.");
      }
      const blob=await response.blob();
      const name=(response.headers.get("Content-Disposition")??"")
        .split("filename=")[1]?.replace(/"/g,"")??`carteira.${format}`;
      const url=URL.createObjectURL(blob);
      const link=document.createElement("a");
      link.href=url;link.download=name;link.click();
      URL.revokeObjectURL(url);
    });
  },
  addCall:(token:string,store:string,body:{
    client_id:string;seller_id:string;date:string;channel:string;
    outcome:string;next_on:string|null;note:string
  }) => request<ContactRow>(token,`/api/v1/operations/contacts/${store}/calls`,"POST",body),
  correctCall:(token:string,store:string,id:string,body:{
    date:string;channel:string;outcome:string;next_on:string|null;note:string;
    expected_revision:number
  }) => request<ContactRow>(token,`/api/v1/operations/contacts/${store}/calls/${id}`,"PUT",body),
};

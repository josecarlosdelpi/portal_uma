import {request} from "./api";

export type VersionInfo={
  id:string;version_label:string;status:"rascunho"|"publicado";revision:number;
  created_at:string;published_at:string|null;content_html?:string
};
export type Procedure={
  id:string;code:string;title:string;summary:string;applies_to_all:boolean;
  stores:string[];current_version:VersionInfo|null;draft_version:VersionInfo|null;
  updated_at:string;content_html?:string;version?:VersionInfo|null
};
export type ProcedurePayload={
  title:string;summary:string;applies_to_all:boolean;store_codes:string[];
  content_html:string;expected_revision?:number
};

export const proceduresApi={
  list:(token:string,params:{status?:"rascunho"|"publicado";store?:string;q?:string}={})=>{
    const qs=new URLSearchParams();
    if(params.status)qs.set("status",params.status);
    if(params.store)qs.set("store",params.store);
    if(params.q)qs.set("q",params.q);
    const suffix=qs.toString()?"?"+qs.toString():"";
    return request<Procedure[]>(token,`/api/v1/procedures${suffix}`);
  },
  get:(token:string,id:string)=>request<Procedure>(token,`/api/v1/procedures/${id}`),
  create:(token:string,body:ProcedurePayload)=>
    request<Procedure>(token,"/api/v1/procedures","POST",body),
  save:(token:string,id:string,body:ProcedurePayload&{expected_revision:number})=>
    request<Procedure>(token,`/api/v1/procedures/${id}`,"PUT",body),
  publish:(token:string,id:string,expectedRevision:number)=>
    request<Procedure>(token,`/api/v1/procedures/${id}/publish`,"POST",
      {expected_revision:expectedRevision}),
  versions:(token:string,id:string)=>
    request<VersionInfo[]>(token,`/api/v1/procedures/${id}/versions`),
  getVersion:(token:string,id:string,versionId:string)=>
    request<VersionInfo>(token,`/api/v1/procedures/${id}/versions/${versionId}`),
  uploadFile:async(token:string,id:string,file:File)=>{
    const form=new FormData();
    form.append("file",file);
    const baseUrl=(import.meta.env.VITE_API_BASE_URL??"").replace(/\/$/,"");
    const response=await fetch(baseUrl+`/api/v1/procedures/${id}/files`,{
      method:"PUT",headers:{Authorization:`Bearer ${token}`},body:form,
    });
    const text=await response.text();
    const payload=text?JSON.parse(text):null;
    if(!response.ok){
      const detail=payload?.detail??response.statusText;
      throw new Error(typeof detail==="string"?detail:"Falha no upload");
    }
    return payload as {id:string;url:string;media_type:string;size:number};
  },
};

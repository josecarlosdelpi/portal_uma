import {request} from "./api";

export type WeeklyTask = {
  id:string;title:string;details:string;frequency:"weekly"|"once";day:number;done:boolean
};
export type WeeklySnapshot={
  store_code:string;week_start:string;week_end:string;items:WeeklyTask[];
  calls:{count:number;target:number;reached:boolean;confirmed:boolean}
};
export type PrivateFileInfo={
  name:string;media_type:string;size:number;revision:number
};
export type WhatsAppPost={
  date:string;product_code:string;category:string;note:string;
  status:"planejado"|"arte_pronta"|"publicado";published_on:string|null;
  revision:number;has_art_file:boolean;has_evidence_file:boolean;
  files:{art?:PrivateFileInfo;evidence?:PrivateFileInfo}
};
export type WhatsAppSnapshot={
  year:number;month:number;scope:string;posts:WhatsAppPost[];
  days_off:{date:string;reason:string}[];attachments_enabled:boolean
};
export type InstagramRow={
  store_code:string;planned:number|null;completed:number|null;revision:number
};
export type InstagramSnapshot={year:number;month:number;stores:InstagramRow[]};
export type TrainingEntry={
  id:string;store_code:string;participant_id:string;participant:string;procedure:string;
  version:string;title:string;instructor:string;happened_on:string;
  step:"participou"|"pratica";note:string;signed:false;
  document_attached:boolean;document:PrivateFileInfo|null
};

export const routinesApi={
  weekly:(token:string,store:string,day:string)=>
    request<WeeklySnapshot>(token,`/api/v1/routines/checklist/${store}/${day}`),
  createTask:(token:string,store:string,body:{
    reference:string;title:string;details:string;frequency:"weekly"|"once";day:number
  })=>request<{id:string}>(token,`/api/v1/routines/checklist/${store}/tasks`,"POST",body),
  reviseTask:(token:string,store:string,id:string,body:{
    reference:string;title:string;details:string;frequency:"weekly"|"once";day:number
  })=>request<{id:string}>(token,`/api/v1/routines/checklist/${store}/tasks/${id}`,"PUT",body),
  verifyTask:(token:string,store:string,id:string,reference:string,done:boolean)=>
    request<{done:boolean}>(token,`/api/v1/routines/checklist/${store}/tasks/${id}/check`,
      "PUT",{reference,done}),
  callGoal:(token:string,store:string,reference:string,goal:number,confirmed:boolean)=>
    request<{goal:number;confirmed:boolean}>(token,`/api/v1/routines/checklist/${store}/calls-goal`,
      "PUT",{reference,goal,confirmed}),
  whatsapp:(token:string,year:number,month:number)=>
    request<WhatsAppSnapshot>(token,`/api/v1/routines/whatsapp/${year}/${month}`),
  saveWhatsApp:(token:string,day:string,body:{
    product_code:string;category:string;note:string;
    status:"planejado"|"arte_pronta"|"publicado";expected_revision:number
  })=>request<WhatsAppPost>(token,`/api/v1/routines/whatsapp/${day}`,"PUT",body),
  deleteWhatsApp:(token:string,day:string,expectedRevision:number)=>
    request<{date:string;deleted:boolean}>(token,`/api/v1/routines/whatsapp/${day}`,
      "DELETE",{expected_revision:expectedRevision}),
  dayOff:(token:string,day:string,off:boolean,reason:string)=>
    request<{date:string;off:boolean}>(token,`/api/v1/routines/whatsapp/${day}/day-off`,
      "PUT",{off,reason}),
  instagram:(token:string,year:number,month:number)=>
    request<InstagramSnapshot>(token,`/api/v1/routines/instagram/${year}/${month}`),
  saveInstagram:(token:string,store:string,year:number,month:number,
                planned:number,completed:number,expected_revision:number)=>
    request<InstagramRow>(token,`/api/v1/routines/instagram/${store}/${year}/${month}`,
      "PUT",{planned,completed,expected_revision}),
  trainings:(token:string,store:string)=>
    request<TrainingEntry[]>(token,`/api/v1/routines/trainings/${store}`),
  addTraining:(token:string,store:string,body:{
    participant_id:string;procedure:string;version:string;title:string;
    instructor:string;happened_on:string;step:"participou"|"pratica";note:string
  })=>request<TrainingEntry>(token,`/api/v1/routines/trainings/${store}`,"POST",body)
};

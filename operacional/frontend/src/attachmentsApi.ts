import {ApiError} from "./api";
import type {PrivateFileInfo} from "./routinesApi";

const base=(import.meta.env.VITE_API_BASE_URL??"").replace(/[/]$/,"");

async function parse(response:Response){
  if(response.ok)return response;
  let reason="Não foi possível acessar o anexo privado.";
  if(response.status===401)reason="Sessão inválida ou expirada. Entre novamente.";
  else if(response.status===403)reason="Seu perfil não permite esta operação.";
  else if(response.status===404)reason="Arquivo ou registro não encontrado.";
  else if(response.status===409)reason="O anexo foi alterado. Atualize a tela.";
  else if(response.status===413)reason="Arquivo acima do limite permitido.";
  else if(response.status===422)reason="Formato de arquivo inválido. Verifique o tipo e a extensão.";
  throw new ApiError(response.status,reason);
}

async function upload(token:string,route:string,file:File,limit:number):Promise<PrivateFileInfo>{
  if(file.size===0||file.size>limit)
    throw new Error("Escolha um arquivo de até "+Math.floor(limit/1024/1024)+" MB.");
  const data=new FormData();
  data.append("file",file,file.name);
  const response=await fetch(base+route,{
    method:"PUT",cache:"no-store",mode:"cors",
    headers:{Authorization:"Bearer "+token},
    body:data,
  });
  await parse(response);
  return response.json() as Promise<PrivateFileInfo>;
}

async function remove(token:string,route:string):Promise<void>{
  const response=await fetch(base+route,{
    method:"DELETE",cache:"no-store",mode:"cors",
    headers:{Authorization:"Bearer "+token},
  });
  await parse(response);
}

async function download(token:string,route:string,filename:string):Promise<void>{
  const response=await fetch(base+route,{
    method:"GET",cache:"no-store",mode:"cors",
    headers:{Authorization:"Bearer "+token},
  });
  await parse(response);
  const blob=await response.blob();
  const url=URL.createObjectURL(blob);
  const link=document.createElement("a");
  link.href=url;
  link.download=filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(()=>URL.revokeObjectURL(url),1000);
}

export const attachmentsApi={
  uploadWhatsApp:(token:string,day:string,kind:"art"|"evidence",
                  file:File,expected:number)=>
    upload(token,`/api/v1/routines/whatsapp/${day}/files/${kind}?expected_revision=${expected}`,
      file,3*1024*1024),
  downloadWhatsApp:(token:string,day:string,kind:"art"|"evidence",name:string)=>
    download(token,`/api/v1/routines/whatsapp/${day}/files/${kind}`,name),
  deleteWhatsApp:(token:string,day:string,kind:"art"|"evidence",expected:number)=>
    remove(token,`/api/v1/routines/whatsapp/${day}/files/${kind}?expected_revision=${expected}`),
  uploadTraining:(token:string,store:string,id:string,file:File,expected:number)=>
    upload(token,`/api/v1/routines/trainings/${store}/${id}/document?expected_revision=${expected}`,
      file,5*1024*1024),
  downloadTraining:(token:string,store:string,id:string,name:string)=>
    download(token,`/api/v1/routines/trainings/${store}/${id}/document`,name),
  deleteTraining:(token:string,store:string,id:string,expected:number)=>
    remove(token,`/api/v1/routines/trainings/${store}/${id}/document?expected_revision=${expected}`),
};

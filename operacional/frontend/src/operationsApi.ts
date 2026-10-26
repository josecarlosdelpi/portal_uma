import {request} from "./api";
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
  id:string;store_code:string;name:string;phone:string|null;erp_code:string|null;
  origin:string;last_purchase_on:string|null
};
export type TeamMember = {id:string;name:string};
export type ContactRow = {
  id:string;store_code:string;client_id:string;client:string;
  seller_id:string;seller:string;date:string;outcome:string;next_on:string|null;
  note:string;revision:number
};
export type CallsSnapshot = {store_code:string;year:number;month:number;items:ContactRow[]};

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
  clients:(token:string,store:string) =>
    request<ClientRow[]>(token,`/api/v1/operations/contacts/${store}/clients`),
  addClient:(token:string,store:string,body:{
    name:string;phone:string|null;erp_code:string|null;origin:string;
    last_purchase_on:string|null
  }) => request<ClientRow>(token,`/api/v1/operations/contacts/${store}/clients`,"POST",body),
  team:(token:string,store:string) =>
    request<TeamMember[]>(token,`/api/v1/operations/contacts/${store}/team`),
  calls:(token:string,store:string,year:number,month:number) =>
    request<CallsSnapshot>(token,`/api/v1/operations/contacts/${store}/${year}/${month}/calls`),
  addCall:(token:string,store:string,body:{
    client_id:string;seller_id:string;date:string;outcome:string;next_on:string|null;note:string
  }) => request<ContactRow>(token,`/api/v1/operations/contacts/${store}/calls`,"POST",body),
  correctCall:(token:string,store:string,id:string,body:{
    date:string;outcome:string;next_on:string|null;note:string;expected_revision:number
  }) => request<ContactRow>(token,`/api/v1/operations/contacts/${store}/calls/${id}`,"PUT",body),
};

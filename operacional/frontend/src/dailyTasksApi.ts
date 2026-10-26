import {request} from "./api";

export type DailyTaskStatus = "pendente"|"em_andamento"|"concluida";
export type DailyPriority = "baixa"|"normal"|"alta";
export type DailyTask = {
  id:string;store_code:string;date:string;title:string;details:string;
  priority:DailyPriority;status:DailyTaskStatus;assignee_id:string|null;
  assignee:string;completed_at:string|null;revision:number;
};
export type DailySnapshot = {
  store_code:string;date:string;items:DailyTask[];
  summary:{total:number;pending:number;in_progress:number;completed:number};
};
export type DailyNew = {
  date:string;title:string;details:string;priority:DailyPriority;assignee_id:string|null;
};
export type DailyEdit = DailyNew & {
  status:DailyTaskStatus;expected_revision:number;
};

export const dailyTasksApi={
  day:(token:string,store:string,date:string)=>
    request<DailySnapshot>(token,`/api/v1/daily-tasks/${store}/${date}`),
  create:(token:string,store:string,body:DailyNew)=>
    request<DailyTask>(token,`/api/v1/daily-tasks/${store}`,"POST",body),
  edit:(token:string,store:string,id:string,body:DailyEdit)=>
    request<DailyTask>(token,`/api/v1/daily-tasks/${store}/${id}`,"PUT",body),
  remove:(token:string,store:string,id:string,expected_revision:number)=>
    request<{id:string;deleted:boolean}>(token,`/api/v1/daily-tasks/${store}/${id}`,
      "DELETE",{expected_revision}),
};

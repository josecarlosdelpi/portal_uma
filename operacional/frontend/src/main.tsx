import React from "react";
import {createRoot} from "react-dom/client";
import {AuthProvider,useAuth} from "react-oidc-context";
import {WebStorageStateStore} from "oidc-client-ts";

import {App} from "./App";
import {LocalAccess} from "./LocalAccess";
import "./styles.css";
import "./institutional-theme.css";

const authority=import.meta.env.VITE_OIDC_AUTHORITY;
const clientId=import.meta.env.VITE_OIDC_CLIENT_ID;
const configured=Boolean(authority&&clientId);

function OptionalOidc(){
  const auth=useAuth();
  if(auth.isAuthenticated&&auth.user?.access_token){
    return <App token={auth.user.access_token}
      onLogout={()=>void auth.signoutRedirect()}/>;
  }
  return <LocalAccess onUseExternalLogin={()=>void auth.signinRedirect()}
    externalError={auth.error?.message}/>;
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    {configured?<AuthProvider
      authority={authority}
      client_id={clientId}
      redirect_uri={import.meta.env.VITE_OIDC_REDIRECT_URI||
        window.location.origin+window.location.pathname}
      response_type="code"
      scope="openid profile"
      automaticSilentRenew={false}
      userStore={new WebStorageStateStore({store:window.sessionStorage})}
      onSigninCallback={()=>{
        window.history.replaceState({},document.title,window.location.pathname);
      }}
    ><OptionalOidc/></AuthProvider>:<LocalAccess/>}
  </React.StrictMode>
);

import React from "react";
import { createRoot } from "react-dom/client";
import { AuthProvider } from "react-oidc-context";
import { WebStorageStateStore } from "oidc-client-ts";

import { App } from "./App";
import "./styles.css";

const authority = import.meta.env.VITE_OIDC_AUTHORITY;
const clientId = import.meta.env.VITE_OIDC_CLIENT_ID;
const configured = Boolean(authority && clientId);

const root = createRoot(document.getElementById("root")!);
root.render(
  <React.StrictMode>
    {configured ? (
      <AuthProvider
        authority={authority}
        client_id={clientId}
        redirect_uri={import.meta.env.VITE_OIDC_REDIRECT_URI || window.location.origin + window.location.pathname}
        response_type="code"
        scope="openid profile email"
        automaticSilentRenew={false}
        userStore={new WebStorageStateStore({ store: window.sessionStorage })}
        onSigninCallback={() => {
          window.history.replaceState({}, document.title, window.location.pathname);
        }}
      >
        <App />
      </AuthProvider>
    ) : (
      <div className="login-stage">
        <main className="login-panel" aria-labelledby="setup-title">
          <div className="login-brand">UMA <span>•</span> PORTAL</div>
          <div className="eyebrow">Versão operacional</div>
          <h1 id="setup-title">Acesso seguro em preparação</h1>
          <p>
            A interface está sendo desenvolvida. A integração com o serviço de autenticação
            será configurada antes de habilitar os acessos dos colaboradores.
          </p>
          <div className="notice notice-amber">
            Não existem credenciais de demonstração para esta versão.
            Nenhum dado comercial real é utilizado.
          </div>
        </main>
      </div>
    )}
  </React.StrictMode>,
);

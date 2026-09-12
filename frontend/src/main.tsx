import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { ScopeProvider } from "./api/scope";
import { I18nProvider } from "./i18n";
import { CurrencyProvider } from "./lib/currency";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <I18nProvider>
      <CurrencyProvider>
        <ScopeProvider>
          <App />
        </ScopeProvider>
      </CurrencyProvider>
    </I18nProvider>
  </React.StrictMode>,
);

import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { App } from './ui/App';
import { loadMaxBridge } from './api/maxAuth';
import { APP_BASE, PREVIEW_MODE } from './api/appConfig';
import './ui/style.css';

async function start(): Promise<void> {
  if (!import.meta.env.DEV && !PREVIEW_MODE) {
    await loadMaxBridge();
  }
  if (import.meta.env.DEV && !PREVIEW_MODE && import.meta.env.VITE_ENABLE_MOCK === 'true') {
    const { worker } = await import('./mock/browser');
    await worker.start({ onUnhandledRequest: 'bypass', serviceWorker: { url: `${APP_BASE}mockServiceWorker.js` } });
  }
  ReactDOM.createRoot(document.getElementById('root')!).render(
    <React.StrictMode><BrowserRouter basename={APP_BASE.slice(0, -1)}><App /></BrowserRouter></React.StrictMode>,
  );
}

void start();

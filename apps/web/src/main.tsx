import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { App } from './ui/App';
import './ui/style.css';

async function start(): Promise<void> {
  if (import.meta.env.DEV && import.meta.env.VITE_ENABLE_MOCK === 'true') {
    const { worker } = await import('./mock/browser');
    await worker.start({ onUnhandledRequest: 'bypass', serviceWorker: { url: '/team/zhkh/mockServiceWorker.js' } });
  }
  ReactDOM.createRoot(document.getElementById('root')!).render(
    <React.StrictMode><BrowserRouter basename="/team/zhkh"><App /></BrowserRouter></React.StrictMode>,
  );
}

void start();

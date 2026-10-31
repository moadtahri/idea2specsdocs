import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import { applyStoredTheme } from './theme';
// Kanya's look (spec 09): Canyas tokens, base, layout and chat styles, then itos's own pieces.
import './styles/tokens.css';
import './styles/base.css';
import './styles/app.css';
import './styles/kanya.css';
import './components/chat/reply-tools.css';
import './components/chat/voice.css';
import './styles/itos.css';

applyStoredTheme();

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);

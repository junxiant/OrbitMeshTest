import { useState, useRef, useEffect } from 'react';
import { sendMessage } from './api';
import './App.css';

function generateSessionId() {
  return 'session-' + Math.random().toString(36).substring(2, 9);
}

const STORAGE_KEY = 'orbitmesh_chat_sessions';

function loadStoredSessions() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed) && parsed.length > 0) {
        return parsed;
      }
    }
  } catch (e) {
    console.error('Failed to parse sessions from storage:', e);
  }
  return null;
}

function saveStoredSessions(sessions) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions));
  } catch (e) {
    console.error('Failed to save sessions to storage:', e);
  }
}

const PlusIcon = () => (
  <svg className="icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <line x1="12" y1="5" x2="12" y2="19" />
    <line x1="5" y1="12" x2="19" y2="12" />
  </svg>
);

const SidebarIcon = () => (
  <svg className="icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
    <line x1="9" y1="3" x2="9" y2="21" />
  </svg>
);

const ChatIcon = () => (
  <svg className="icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
  </svg>
);

const TrashIcon = () => (
  <svg className="icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="3 6 5 6 21 6" />
    <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
  </svg>
);

export default function App() {
  const initialSessionId = generateSessionId();

  const [sessions, setSessions] = useState(() => {
    const stored = loadStoredSessions();
    if (stored) return stored;
    return [
      {
        id: initialSessionId,
        title: 'New Conversation',
        createdAt: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        messages: [
          {
            id: 'welcome',
            sender: 'assistant',
            text: 'Hello. I am the OrbitMesh Support Assistant. How can I assist you with your router or mesh nodes today?',
            citations: [],
            action: 'instruct',
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          },
        ],
      },
    ];
  });

  const [activeSessionId, setActiveSessionId] = useState(() => {
    const stored = loadStoredSessions();
    return stored && stored.length > 0 ? stored[0].id : initialSessionId;
  });

  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const messagesEndRef = useRef(null);

  const currentSession = sessions.find((s) => s.id === activeSessionId) || sessions[0];
  const messages = currentSession ? currentSession.messages : [];

  useEffect(() => {
    saveStoredSessions(sessions);
  }, [sessions]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, loading]);

  const handleStartNewChat = () => {
    const newId = generateSessionId();
    const newSession = {
      id: newId,
      title: 'New Conversation',
      createdAt: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      messages: [
        {
          id: 'welcome-' + Date.now(),
          sender: 'assistant',
          text: 'Hello. How can I assist you with your OrbitMesh system?',
          citations: [],
          action: 'instruct',
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        },
      ],
    };

    setSessions((prev) => [newSession, ...prev]);
    setActiveSessionId(newId);
    setError(null);
  };

  const handleSelectSession = (id) => {
    setActiveSessionId(id);
    setError(null);
  };

  const handleDeleteSession = (e, id) => {
    e.stopPropagation();
    if (sessions.length === 1) {
      handleStartNewChat();
      return;
    }
    const filtered = sessions.filter((s) => s.id !== id);
    setSessions(filtered);
    if (activeSessionId === id) {
      setActiveSessionId(filtered[0].id);
    }
  };

  const handleSend = async (messageText) => {
    const textToSend = (messageText || input).trim();
    if (!textToSend || loading) return;

    const userMessage = {
      id: 'user-' + Date.now(),
      sender: 'user',
      text: textToSend,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };

    const isFirstUserMessage = messages.filter((m) => m.sender === 'user').length === 0;
    const sessionTitle = isFirstUserMessage
      ? textToSend.length > 28
        ? textToSend.substring(0, 28) + '...'
        : textToSend
      : currentSession.title;

    setSessions((prev) =>
      prev.map((s) => {
        if (s.id === activeSessionId) {
          return {
            ...s,
            title: sessionTitle,
            messages: [...s.messages, userMessage],
          };
        }
        return s;
      })
    );

    setInput('');
    setLoading(true);
    setError(null);

    try {
      const data = await sendMessage(activeSessionId, textToSend);

      const assistantMessage = {
        id: 'assistant-' + Date.now(),
        sender: 'assistant',
        text: data.response || 'No response returned.',
        citations: data.citations || [],
        action: data.action || 'instruct',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };

      setSessions((prev) =>
        prev.map((s) => {
          if (s.id === activeSessionId) {
            return {
              ...s,
              messages: [...s.messages, assistantMessage],
            };
          }
          return s;
        })
      );
    } catch (err) {
      setError(err.message || 'Failed to send message');
      setSessions((prev) =>
        prev.map((s) => {
          if (s.id === activeSessionId) {
            return {
              ...s,
              messages: [
                ...s.messages,
                {
                  id: 'error-' + Date.now(),
                  sender: 'assistant',
                  text: 'Error: Unable to connect to backend server. Ensure backend is running.',
                  citations: [],
                  action: 'error',
                  timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
                },
              ],
            };
          }
          return s;
        })
      );
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const quickQueries = [
    'My N1 node has a solid amber light',
    'How do I perform a factory reset?',
    'What is the warranty coverage?',
  ];

  return (
    <div className="layout-root">
      {/* Left Sidebar */}
      <aside className={`sidebar ${isSidebarOpen ? 'expanded' : 'collapsed'}`}>
        {isSidebarOpen ? (
          /* Expanded Sidebar View */
          <div className="sidebar-expanded-content">
            <div className="sidebar-header">
              <div className="sidebar-brand">
                <ChatIcon />
                <h2>History</h2>
              </div>
              <button
                className="sidebar-toggle-btn"
                onClick={() => setIsSidebarOpen(false)}
                title="Collapse sidebar"
              >
                <SidebarIcon />
              </button>
            </div>

            <button className="new-chat-btn" onClick={handleStartNewChat}>
              <PlusIcon />
              <span>New Chat</span>
            </button>

            <div className="sessions-list">
              {sessions.map((s) => (
                <div
                  key={s.id}
                  className={`session-item ${s.id === activeSessionId ? 'active' : ''}`}
                  onClick={() => handleSelectSession(s.id)}
                >
                  <div className="session-item-content">
                    <span className="session-title">{s.title}</span>
                    <span className="session-time">{s.createdAt}</span>
                  </div>
                  <button
                    className="session-delete-btn"
                    onClick={(e) => handleDeleteSession(e, s.id)}
                    title="Delete conversation"
                  >
                    <TrashIcon />
                  </button>
                </div>
              ))}
            </div>

            <div className="sidebar-footer">
              <span>{sessions.length} {sessions.length === 1 ? 'chat' : 'chats'}</span>
            </div>
          </div>
        ) : (
          /* Collapsed Mini-Rail View */
          <div className="sidebar-mini-rail">
            <button
              className="mini-icon-btn"
              onClick={() => setIsSidebarOpen(true)}
              title="Expand history"
            >
              <SidebarIcon />
            </button>

            <button
              className="mini-icon-btn new-chat-mini"
              onClick={handleStartNewChat}
              title="New Chat"
            >
              <PlusIcon />
            </button>

            <div className="mini-separator" />

            <div className="mini-sessions">
              {sessions.slice(0, 5).map((s) => (
                <button
                  key={s.id}
                  className={`mini-session-dot ${s.id === activeSessionId ? 'active' : ''}`}
                  onClick={() => handleSelectSession(s.id)}
                  title={s.title}
                >
                  <ChatIcon />
                </button>
              ))}
            </div>
          </div>
        )}
      </aside>

      {/* Main Chat Interface */}
      <main className="chat-main">
        <header className="chat-header">
          <div className="header-left">
            <div className="header-title-group">
              <h1>OrbitMesh Support Assistant</h1>
              <span className="session-tag">Session ID: {activeSessionId}</span>
            </div>
          </div>
        </header>

        {error && <div className="error-banner">{error}</div>}

        <div className="messages-area">
          <div className="messages-inner">
            {messages.map((msg) => (
              <div key={msg.id} className={`message-row ${msg.sender}`}>
                <div className="message-bubble">
                  <div className="message-meta">
                    <span className="message-sender">
                      {msg.sender === 'user' ? 'You' : 'OrbitMesh Support'}
                    </span>
                    <span className="message-time">{msg.timestamp}</span>
                  </div>

                  <div className="message-content">{msg.text}</div>

                  {msg.action && msg.sender === 'assistant' && (
                    <div className="message-action">
                      <span className={`action-badge ${msg.action}`}>
                        Action: {msg.action}
                      </span>
                    </div>
                  )}

                  {msg.citations && msg.citations.length > 0 && (
                    <div className="citations-block">
                      <span className="citations-title">Sources:</span>
                      <ul>
                        {msg.citations.map((c, i) => (
                          <li key={i}>
                            <strong>{c.source_id}</strong>: {c.locator}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              </div>
            ))}

            {loading && (
              <div className="message-row assistant">
                <div className="message-bubble loading-bubble">
                  <span>Assistant is analyzing...</span>
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>
        </div>

        <div className="quick-queries">
          <div className="quick-queries-inner">
            {quickQueries.map((q, idx) => (
              <button
                key={idx}
                className="query-chip"
                onClick={() => handleSend(q)}
                disabled={loading}
              >
                {q}
              </button>
            ))}
          </div>
        </div>

        <footer className="input-footer">
          <form
            className="input-form"
            onSubmit={(e) => {
              e.preventDefault();
              handleSend();
            }}
          >
            <input
              type="text"
              className="chat-input"
              placeholder="Ask a question about your OrbitMesh router, node LEDs, reset procedures..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={loading}
            />
            <button
              type="submit"
              className="send-button"
              disabled={loading || !input.trim()}
            >
              Send
            </button>
          </form>
        </footer>
      </main>
    </div>
  );
}

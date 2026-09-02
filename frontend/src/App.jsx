import { useState, useRef, useEffect } from 'react';
import { sendMessage } from './api';
import './App.css';

function generateSessionId() {
  return 'session-' + Math.random().toString(36).substring(2, 9);
}

export default function App() {
  const [sessionId, setSessionId] = useState(() => generateSessionId());
  const [messages, setMessages] = useState([
    {
      id: 'welcome',
      sender: 'assistant',
      text: 'Hello. I am the OrbitMesh Support Assistant. How can I assist you with your router or mesh nodes today?',
      citations: [],
      action: 'instruct',
      timestamp: new Date().toLocaleTimeString(),
    },
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, loading]);

  const handleSend = async (messageText) => {
    const textToSend = (messageText || input).trim();
    if (!textToSend || loading) return;

    const userMessage = {
      id: 'user-' + Date.now(),
      sender: 'user',
      text: textToSend,
      timestamp: new Date().toLocaleTimeString(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setLoading(true);
    setError(null);

    try {
      const data = await sendMessage(sessionId, textToSend);

      const assistantMessage = {
        id: 'assistant-' + Date.now(),
        sender: 'assistant',
        text: data.response || 'No response returned.',
        citations: data.citations || [],
        action: data.action || 'instruct',
        timestamp: new Date().toLocaleTimeString(),
      };

      setMessages((prev) => [...prev, assistantMessage]);
    } catch (err) {
      setError(err.message || 'Failed to send message');
      setMessages((prev) => [
        ...prev,
        {
          id: 'error-' + Date.now(),
          sender: 'assistant',
          text: 'Error: Unable to connect to the backend server. Please verify the backend service is running.',
          citations: [],
          action: 'error',
          timestamp: new Date().toLocaleTimeString(),
        },
      ]);
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

  const handleResetSession = () => {
    const newId = generateSessionId();
    setSessionId(newId);
    setMessages([
      {
        id: 'welcome-' + Date.now(),
        sender: 'assistant',
        text: 'New session started. How can I assist you with your OrbitMesh system?',
        citations: [],
        action: 'instruct',
        timestamp: new Date().toLocaleTimeString(),
      },
    ]);
    setError(null);
  };

  const quickQueries = [
    'My N1 node has a solid amber light',
    'How do I perform a factory reset?',
    'What is the warranty coverage?',
  ];

  return (
    <div className="chat-app">
      <header className="chat-header">
        <div className="header-info">
          <h1>OrbitMesh Support Assistant</h1>
          <span className="session-tag">Session: {sessionId}</span>
        </div>
        <button className="new-session-btn" onClick={handleResetSession}>
          New Session
        </button>
      </header>

      {error && <div className="error-banner">{error}</div>}

      <main className="messages-container">
        {messages.map((msg) => (
          <div key={msg.id} className={`message-row ${msg.sender}`}>
            <div className="message-bubble">
              <div className="message-header">
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
              <span>Assistant is typing...</span>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </main>

      <div className="quick-queries">
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
            placeholder="Type your question or issue description..."
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
    </div>
  );
}

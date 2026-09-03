import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import App from '../App';
import * as api from '../api';

describe('OrbitMesh Support Assistant Frontend', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it('renders the chatbot interface with initial welcome state', () => {
    render(<App />);

    expect(screen.getByText('OrbitMesh Support Assistant')).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/Ask a question about your OrbitMesh/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Send/i })).toBeInTheDocument();
    expect(screen.getByText(/Hello. I am the OrbitMesh Support Assistant/i)).toBeInTheDocument();
  });

  it('sends query directly when a suggestion chip is clicked', async () => {
    const mockResponse = {
      session_id: 'test-session-chip',
      response: 'Move your N1 node closer to the primary router.',
      citations: [{ source_id: 'led-reference', locator: 'N1 node LEDs' }],
      action: 'instruct',
    };
    vi.spyOn(api, 'sendMessage').mockResolvedValueOnce(mockResponse);

    render(<App />);

    const suggestion = screen.getByText('My N1 node has a solid amber light');
    fireEvent.click(suggestion);

    const matches = screen.getAllByText('My N1 node has a solid amber light');
    expect(matches.length).toBeGreaterThanOrEqual(1);

    await waitFor(() => {
      expect(screen.getByText('Move your N1 node closer to the primary router.')).toBeInTheDocument();
    });
  });

  it('displays user message and assistant reply with action and citations', async () => {
    const mockResponse = {
      session_id: 'test-session-1',
      response: 'Move your N1 node closer to the primary router.',
      citations: [{ source_id: 'led-reference', locator: 'N1 node LEDs' }],
      action: 'instruct',
    };

    vi.spyOn(api, 'sendMessage').mockResolvedValueOnce(mockResponse);

    render(<App />);

    const input = screen.getByPlaceholderText(/Ask a question about your OrbitMesh/i);
    const sendButton = screen.getByRole('button', { name: /Send/i });

    fireEvent.change(input, { target: { value: 'My N1 satellite is amber' } });
    fireEvent.click(sendButton);

    const matches = screen.getAllByText('My N1 satellite is amber');
    expect(matches.length).toBeGreaterThanOrEqual(1);

    await waitFor(() => {
      expect(screen.getByText('Move your N1 node closer to the primary router.')).toBeInTheDocument();
    });

    const actionBadges = screen.getAllByText(/Action:\s*instruct/i);
    expect(actionBadges.length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/led-reference/i)).toBeInTheDocument();
  });

  it('displays an error message when the API request fails', async () => {
    vi.spyOn(api, 'sendMessage').mockRejectedValueOnce(
      new Error('Failed to connect to backend server')
    );

    render(<App />);

    const input = screen.getByPlaceholderText(/Ask a question about your OrbitMesh/i);
    const sendButton = screen.getByRole('button', { name: /Send/i });

    fireEvent.change(input, { target: { value: 'Is the router offline?' } });
    fireEvent.click(sendButton);

    await waitFor(() => {
      expect(
        screen.getByText(/Failed to connect to backend server/i)
      ).toBeInTheDocument();
    });
  });

  it('toggles sidebar collapse state when sidebar button is clicked', () => {
    render(<App />);

    const toggleBtn = screen.getByTitle('Collapse sidebar');
    expect(toggleBtn).toBeInTheDocument();

    fireEvent.click(toggleBtn);

    expect(screen.getByTitle('Expand history')).toBeInTheDocument();
  });

  it('clears active conversation and starts a new session on New Chat click', async () => {
    render(<App />);

    const input = screen.getByPlaceholderText(/Ask a question about your OrbitMesh/i);
    fireEvent.change(input, { target: { value: 'Test query' } });
    fireEvent.click(screen.getByRole('button', { name: /Send/i }));

    const newChatBtn = screen.getByRole('button', { name: /New Chat/i });
    fireEvent.click(newChatBtn);

    expect(screen.getByText(/Hello. How can I assist you with your OrbitMesh system/i)).toBeInTheDocument();
  });

  it('submits query when Enter key is pressed without Shift', async () => {
    const mockResponse = {
      session_id: 'test-session-enter',
      response: 'Rebooting the node resolves this state.',
      citations: [{ source_id: 'troubleshooting-guide', locator: 'Reboot steps' }],
      action: 'instruct',
    };
    vi.spyOn(api, 'sendMessage').mockResolvedValueOnce(mockResponse);

    render(<App />);

    const input = screen.getByPlaceholderText(/Ask a question about your OrbitMesh/i);
    fireEvent.change(input, { target: { value: 'Node is unresponsive' } });
    fireEvent.keyDown(input, { key: 'Enter', shiftKey: false });

    await waitFor(() => {
      expect(screen.getByText('Rebooting the node resolves this state.')).toBeInTheDocument();
    });
  });

  it('does not submit query when Shift+Enter is pressed', () => {
    const sendSpy = vi.spyOn(api, 'sendMessage');

    render(<App />);

    const input = screen.getByPlaceholderText(/Ask a question about your OrbitMesh/i);
    fireEvent.change(input, { target: { value: 'Multi-line query draft' } });
    fireEvent.keyDown(input, { key: 'Enter', shiftKey: true });

    expect(sendSpy).not.toHaveBeenCalled();
    expect(input.value).toBe('Multi-line query draft');
  });

  it('disables send button when input is empty or whitespace-only', () => {
    render(<App />);

    const sendButton = screen.getByRole('button', { name: /Send/i });
    const input = screen.getByPlaceholderText(/Ask a question about your OrbitMesh/i);

    expect(sendButton).toBeDisabled();

    fireEvent.change(input, { target: { value: '   ' } });
    expect(sendButton).toBeDisabled();

    fireEvent.change(input, { target: { value: 'Valid input' } });
    expect(sendButton).not.toBeDisabled();
  });

  it('disables input and send button while request is in flight', async () => {
    let resolvePromise;
    const pendingPromise = new Promise((resolve) => {
      resolvePromise = resolve;
    });
    vi.spyOn(api, 'sendMessage').mockReturnValueOnce(pendingPromise);

    render(<App />);

    const input = screen.getByPlaceholderText(/Ask a question about your OrbitMesh/i);
    const sendButton = screen.getByRole('button', { name: /Send/i });

    fireEvent.change(input, { target: { value: 'Checking status...' } });
    fireEvent.click(sendButton);

    expect(sendButton).toBeDisabled();
    expect(input).toBeDisabled();

    resolvePromise({
      session_id: 'test-pending',
      response: 'Done processing.',
      citations: [],
      action: 'instruct',
    });

    await waitFor(() => {
      expect(screen.getByText('Done processing.')).toBeInTheDocument();
    });

    expect(input).not.toBeDisabled();
  });

  it('switches between multiple conversations in sidebar', async () => {
    vi.spyOn(api, 'sendMessage')
      .mockResolvedValueOnce({
        session_id: 'sess-1',
        response: 'Answer for conversation 1',
        citations: [],
        action: 'instruct',
      })
      .mockResolvedValueOnce({
        session_id: 'sess-2',
        response: 'Answer for conversation 2',
        citations: [],
        action: 'instruct',
      });

    render(<App />);

    const input = screen.getByPlaceholderText(/Ask a question about your OrbitMesh/i);
    fireEvent.change(input, { target: { value: 'Topic 1 query' } });
    fireEvent.click(screen.getByRole('button', { name: /Send/i }));

    await waitFor(() => {
      expect(screen.getByText('Answer for conversation 1')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /New Chat/i }));

    fireEvent.change(screen.getByPlaceholderText(/Ask a question about your OrbitMesh/i), {
      target: { value: 'Topic 2 query' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Send/i }));

    await waitFor(() => {
      expect(screen.getByText('Answer for conversation 2')).toBeInTheDocument();
    });

    const topic1Session = screen.getByText('Topic 1 query');
    fireEvent.click(topic1Session);

    await waitFor(() => {
      expect(screen.getByText('Answer for conversation 1')).toBeInTheDocument();
    });
  });

  it('deletes a conversation from the sidebar', () => {
    render(<App />);

    fireEvent.click(screen.getByRole('button', { name: /New Chat/i }));

    const deleteButtons = screen.getAllByTitle('Delete conversation');
    expect(deleteButtons.length).toBe(2);

    fireEvent.click(deleteButtons[0]);

    expect(screen.getAllByTitle('Delete conversation').length).toBe(1);
  });

  it('loads existing sessions from localStorage on initial mount', () => {
    const savedSessions = [
      {
        id: 'persisted-session-1',
        title: 'Saved Diagnostic Chat',
        createdAt: '10:00 AM',
        messages: [
          {
            id: 'm1',
            sender: 'user',
            text: 'How to check signal strength?',
            timestamp: '10:00 AM',
          },
          {
            id: 'm2',
            sender: 'assistant',
            text: 'Check the LED color on the front panel.',
            citations: [{ source_id: 'led-guide', locator: 'Signal section' }],
            action: 'instruct',
            timestamp: '10:01 AM',
          },
        ],
      },
    ];
    localStorage.setItem('orbitmesh_chat_sessions', JSON.stringify(savedSessions));

    render(<App />);

    expect(screen.getByText('Saved Diagnostic Chat')).toBeInTheDocument();
    expect(screen.getByText('How to check signal strength?')).toBeInTheDocument();
    expect(screen.getByText('Check the LED color on the front panel.')).toBeInTheDocument();
  });
});

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

    // User message bubble and sidebar title appear
    const matches = screen.getAllByText('My N1 node has a solid amber light');
    expect(matches.length).toBeGreaterThanOrEqual(1);

    // Assistant reply should appear
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

    // User message bubble and sidebar title appear
    const matches = screen.getAllByText('My N1 satellite is amber');
    expect(matches.length).toBeGreaterThanOrEqual(1);

    // Assistant response should render
    await waitFor(() => {
      expect(screen.getByText('Move your N1 node closer to the primary router.')).toBeInTheDocument();
    });

    // Citations and action badge should be present
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

    // After clicking, button title toggles to expand history in collapsed mini-rail
    expect(screen.getByTitle('Expand history')).toBeInTheDocument();
  });

  it('clears active conversation and starts a new session on New Chat click', async () => {
    render(<App />);

    const input = screen.getByPlaceholderText(/Ask a question about your OrbitMesh/i);
    fireEvent.change(input, { target: { value: 'Test query' } });
    fireEvent.click(screen.getByRole('button', { name: /Send/i }));

    const newChatBtn = screen.getByRole('button', { name: /New Chat/i });
    fireEvent.click(newChatBtn);

    // Welcome message is restored
    expect(screen.getByText(/Hello. How can I assist you with your OrbitMesh system/i)).toBeInTheDocument();
  });
});

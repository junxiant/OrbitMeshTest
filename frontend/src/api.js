const API_BASE_URL = import.meta.env.VITE_API_URL || '';
const API_KEY = import.meta.env.VITE_API_KEY || '';

export async function sendMessage(sessionId, message) {
  const url = `${API_BASE_URL}/api/chat`;
  const headers = {
    'Content-Type': 'application/json',
  };

  if (API_KEY) {
    headers['X-API-Key'] = API_KEY;
  }

  const response = await fetch(url, {
    method: 'POST',
    headers,
    body: JSON.stringify({
      session_id: sessionId,
      message: message,
    }),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`API error (${response.status}): ${errorText || response.statusText}`);
  }

  return await response.json();
}

export async function streamMessage(sessionId, message, callbacks) {
  const { onChunk, onCitations, onDone, onError } = callbacks;
  const url = `${API_BASE_URL}/api/chat/stream`;
  const headers = {
    'Content-Type': 'application/json',
  };

  if (API_KEY) {
    headers['X-API-Key'] = API_KEY;
  }

  try {
    const response = await fetch(url, {
      method: 'POST',
      headers,
      body: JSON.stringify({
        session_id: sessionId,
        message: message,
      }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`API error (${response.status}): ${errorText || response.statusText}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const packets = buffer.split('\n\n');
      buffer = packets.pop();

      for (const packet of packets) {
        if (!packet.trim()) continue;
        let event = 'message';
        let data = '';

        for (const line of packet.split('\n')) {
          if (line.startsWith('event: ')) {
            event = line.substring(7).trim();
          } else if (line.startsWith('data: ')) {
            data = line.substring(6).trim();
          }
        }

        if (!data) continue;
        try {
          const parsed = JSON.parse(data);
          if (event === 'delta' && onChunk) {
            onChunk(parsed.delta);
          } else if (event === 'replace' && onChunk) {
            onChunk(parsed.response, true);
          } else if (event === 'citations' && onCitations) {
            onCitations(parsed.citations);
          } else if (event === 'done' && onDone) {
            onDone(parsed);
          } else if (event === 'error' && onError) {
            onError(new Error(parsed.error || 'Stream error'));
          }
        } catch (e) {
          console.warn('Failed to parse SSE packet:', data, e);
        }
      }
    }
  } catch (err) {
    if (onError) {
      onError(err);
    } else {
      throw err;
    }
  }
}

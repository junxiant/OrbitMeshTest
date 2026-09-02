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

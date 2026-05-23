import type { RequestHandler } from './$types';

export const GET: RequestHandler = async ({ params, url, request }) => {
	const resp = await fetch(`http://localhost:2026/v1/sessions/${params.id}/events/stream${url.search}`, {
		headers: {
			'Accept': 'text/event-stream',
			'Last-Event-ID': request.headers.get('last-event-id') || '',
		},
		signal: request.signal,
	});

	if (!resp.ok) {
		const text = await resp.text().catch(() => 'Backend stream error');
		console.error('[SSE proxy] backend error', resp.status, text);
		return new Response(text, {
			status: resp.status,
			headers: { 'Content-Type': 'text/plain' },
		});
	}

	return new Response(resp.body, {
		status: resp.status,
		headers: {
			'Content-Type': 'text/event-stream',
			'Cache-Control': 'no-cache',
			'Connection': 'keep-alive',
			'X-Accel-Buffering': 'no',
		},
	});
};

export const prerender = false;

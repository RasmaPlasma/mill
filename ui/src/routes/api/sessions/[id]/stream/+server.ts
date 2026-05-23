import type { RequestHandler } from './$types';

export const GET: RequestHandler = async ({ params, url, request }) => {
	const runId = url.searchParams.get('run_id');
	const qs = runId ? `?run_id=${encodeURIComponent(runId)}` : '';
	const resp = await fetch(`http://localhost:2026/v1/sessions/${params.id}/stream${qs}`, {
		headers: {
			'Accept': 'text/event-stream',
			'Last-Event-ID': request.headers.get('last-event-id') || '',
		},
		signal: request.signal,
	});

	// If backend returns non-OK, return the error as a plain text response
	// so the browser EventSource gets a transport error instead of garbled SSE
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

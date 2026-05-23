import type { RequestHandler } from './$types';

export const GET: RequestHandler = async ({ params, url }) => {
	const limit = url.searchParams.get('limit') || '100';
	const offset = url.searchParams.get('offset') || '0';
	const qs = `?limit=${encodeURIComponent(limit)}&offset=${encodeURIComponent(offset)}`;
	const resp = await fetch(`http://localhost:2026/v1/sessions/${params.id}/events${qs}`);

	if (!resp.ok) {
		const text = await resp.text().catch(() => 'Backend error');
		return new Response(text, { status: resp.status });
	}

	return new Response(resp.body, {
		status: resp.status,
		headers: { 'Content-Type': 'application/json' },
	});
};

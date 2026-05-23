import { env } from '$env/dynamic/private';

const API_BASE = env.API_BASE_URL || 'http://localhost:2026';

export async function apiFetch(path: string, init?: RequestInit) {
	const url = `${API_BASE}${path.startsWith('/') ? '' : '/'}${path}`;
	const resp = await fetch(url, {
		...init,
		headers: {
			'Content-Type': 'application/json',
			...init?.headers,
		},
	});
	if (!resp.ok) {
		const text = await resp.text().catch(() => '');
		throw new Error(`API ${path} → ${resp.status}: ${text}`);
	}
	return resp.status === 204 ? null : resp.json();
}

import { apiFetch } from '$lib/api';
import { fail } from '@sveltejs/kit';
import type { PageServerLoad, Actions } from './$types';

export const load: PageServerLoad = async ({ url }) => {
	const limit = Number(url.searchParams.get('limit') || '50');
	const offset = Number(url.searchParams.get('offset') || '0');
	const qs = new URLSearchParams({ limit: String(limit), offset: String(offset) });
	const data = await apiFetch(`v1/agents?${qs}`);
	return {
		agents: data.items ?? [],
		count: data.count ?? 0,
		limit,
		offset,
	};
};

export const actions: Actions = {
	archive: async ({ request }) => {
		const fd = await request.formData();
		const id = fd.get('id') as string;
		if (!id) return fail(400, { error: 'Missing agent ID' });
		try {
			await apiFetch(`v1/agents/${id}/archive`, { method: 'POST' });
			return { success: true };
		} catch (err: any) {
			return fail(500, { error: err.message });
		}
	},
	bulkArchive: async ({ request }) => {
		const fd = await request.formData();
		const idsRaw = fd.get('ids') as string;
		if (!idsRaw) return fail(400, { error: 'Missing agent IDs' });
		const ids = JSON.parse(idsRaw);
		try {
			await apiFetch('v1/agents/archive', {
				method: 'POST',
				body: JSON.stringify({ ids }),
				headers: { 'Content-Type': 'application/json' },
			});
			return { success: true };
		} catch (err: any) {
			return fail(500, { error: err.message });
		}
	},
};

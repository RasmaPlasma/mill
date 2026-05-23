import { apiFetch } from '$lib/api';
import { sessionCreateSchema } from '$lib/schemas';
import { fail, redirect } from '@sveltejs/kit';
import { superValidate } from 'sveltekit-superforms';
import { zod } from 'sveltekit-superforms/adapters';
import type { PageServerLoad, Actions } from './$types';

export const load: PageServerLoad = async ({ url }) => {
	const limit = Number(url.searchParams.get('limit') || '50');
	const offset = Number(url.searchParams.get('offset') || '0');
	const status = url.searchParams.get('status') || '';

	const qs = new URLSearchParams({ limit: String(limit), offset: String(offset) });
	if (status) qs.append('status', status);

	const [sessionsData, agentsData, envsData] = await Promise.all([
		apiFetch(`v1/sessions?${qs}`),
		apiFetch('v1/agents?limit=100'),
		apiFetch('v1/environments?limit=100'),
	]);

	const agentsMap: Record<string, string> = {};
	for (const a of agentsData.items ?? []) {
		agentsMap[a.id] = a.name;
	}

	const envsMap: Record<string, string> = {};
	for (const e of envsData.items ?? []) {
		envsMap[e.id] = e.name;
	}

	const form = await superValidate(zod(sessionCreateSchema));

	return {
		sessions: sessionsData.items ?? [],
		agentsMap,
		envsMap,
		count: sessionsData.count ?? 0,
		limit,
		offset,
		status,
		form,
		agents: agentsData.items ?? [],
		environments: envsData.items ?? [],
	};
};

export const actions: Actions = {
	archive: async ({ request }) => {
		const fd = await request.formData();
		const id = fd.get('id') as string;
		if (!id) return fail(400, { error: 'Missing session ID' });
		try {
			await apiFetch(`v1/sessions/${id}/archive`, { method: 'POST' });
			return { success: true };
		} catch (err: any) {
			return fail(500, { error: err.message });
		}
	},
	bulkArchive: async ({ request }) => {
		const fd = await request.formData();
		const idsRaw = fd.get('ids') as string;
		if (!idsRaw) return fail(400, { error: 'Missing session IDs' });
		const ids = JSON.parse(idsRaw);
		try {
			await apiFetch('v1/sessions/archive', {
				method: 'POST',
				body: JSON.stringify({ ids }),
				headers: { 'Content-Type': 'application/json' },
			});
			return { success: true };
		} catch (err: any) {
			return fail(500, { error: err.message });
		}
	},
	create: async ({ request }) => {
		const form = await superValidate(request, zod(sessionCreateSchema));
		if (!form.valid) {
			return fail(400, { form });
		}

		const payload: Record<string, any> = {
			agent_id: form.data.agent_id,
			environment_id: form.data.environment_id,
		};
		if (form.data.title) payload.title = form.data.title;
		if (form.data.vault_ids) {
			payload.vault_ids = form.data.vault_ids
				.split(/[\n,]+/)
				.map((s: string) => s.trim())
				.filter(Boolean);
		}
		if (form.data.repositories_json) {
			payload.repositories = JSON.parse(form.data.repositories_json);
		}
		if (form.data.skill_repos_json) {
			payload.skill_repos = JSON.parse(form.data.skill_repos_json);
		}

		try {
			const res = await apiFetch('v1/sessions', {
				method: 'POST',
				body: JSON.stringify(payload),
			});
			return { success: true, session: res, form };
		} catch (err: any) {
			return fail(500, { form, error: err.message });
		}
	},
};

import { apiFetch } from '$lib/api';
import { secretUpsertSchema } from '$lib/schemas';
import { fail } from '@sveltejs/kit';
import { superValidate } from 'sveltekit-superforms';
import { zod } from 'sveltekit-superforms/adapters';
import type { PageServerLoad, Actions } from './$types';

export const load: PageServerLoad = async ({ url }) => {
	const limit = Number(url.searchParams.get('limit') || '50');
	const offset = Number(url.searchParams.get('offset') || '0');
	const scope = url.searchParams.get('scope') || '';

	const qs = new URLSearchParams({ limit: String(limit), offset: String(offset) });
	if (scope) qs.append('scope', scope);

	const [secretsData, agentsData, envsData] = await Promise.all([
		apiFetch(`v1/secrets?${qs}`),
		apiFetch('v1/agents?limit=100').catch(() => ({ items: [] })),
		apiFetch('v1/environments?limit=100').catch(() => ({ items: [] })),
	]);

	const form = await superValidate(zod(secretUpsertSchema));

	return {
		secrets: secretsData.items ?? [],
		count: secretsData.count ?? 0,
		limit,
		offset,
		scope,
		form,
		agents: agentsData.items ?? [],
		environments: envsData.items ?? [],
	};
};

export const actions: Actions = {
	upsert: async ({ request }) => {
		const form = await superValidate(request, zod(secretUpsertSchema));
		if (!form.valid) {
			return fail(400, { form });
		}
		const payload = {
			name: form.data.name,
			value: form.data.value,
			scope: form.data.scope,
			description: form.data.description || undefined,
		};
		try {
			const res = await apiFetch('v1/secrets', {
				method: 'POST',
				body: JSON.stringify(payload),
			});
			return { success: true, secret: res, form };
		} catch (err: any) {
			return fail(500, { form, error: err.message });
		}
	},
	delete: async ({ request }) => {
		const fd = await request.formData();
		const id = fd.get('id') as string;
		if (!id) return fail(400, { error: 'Missing secret ID' });
		try {
			await apiFetch(`v1/secrets/${id}`, { method: 'DELETE' });
			return { success: true };
		} catch (err: any) {
			return fail(500, { error: err.message });
		}
	},
};

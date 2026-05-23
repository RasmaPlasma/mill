import { apiFetch } from '$lib/api';
import { vaultCreateSchema } from '$lib/schemas';
import { fail } from '@sveltejs/kit';
import { superValidate } from 'sveltekit-superforms';
import { zod } from 'sveltekit-superforms/adapters';
import type { PageServerLoad, Actions } from './$types';

export const load: PageServerLoad = async ({ url }) => {
	const limit = Number(url.searchParams.get('limit') || '50');
	const offset = Number(url.searchParams.get('offset') || '0');
	const qs = new URLSearchParams({ limit: String(limit), offset: String(offset) });
	const data = await apiFetch(`v1/vaults?${qs}`);
	const form = await superValidate(zod(vaultCreateSchema));
	return {
		vaults: data.items ?? [],
		count: data.count ?? 0,
		limit,
		offset,
		form,
	};
};

export const actions: Actions = {
	archive: async ({ request }) => {
		const fd = await request.formData();
		const id = fd.get('id') as string;
		if (!id) return fail(400, { error: 'Missing vault ID' });
		try {
			await apiFetch(`v1/vaults/${id}/archive`, { method: 'POST' });
			return { success: true };
		} catch (err: any) {
			return fail(500, { error: err.message });
		}
	},
	bulkArchive: async ({ request }) => {
		const fd = await request.formData();
		const idsRaw = fd.get('ids') as string;
		if (!idsRaw) return fail(400, { error: 'Missing vault IDs' });
		const ids = JSON.parse(idsRaw);
		try {
			await apiFetch('v1/vaults/archive', {
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
		const form = await superValidate(request, zod(vaultCreateSchema));
		if (!form.valid) {
			return fail(400, { form });
		}
		const payload = {
			display_name: form.data.display_name,
			metadata: form.data.metadata_json ? JSON.parse(form.data.metadata_json) : {},
		};
		try {
			const res = await apiFetch('v1/vaults', {
				method: 'POST',
				body: JSON.stringify(payload),
			});
			return { success: true, vault: res, form };
		} catch (err: any) {
			return fail(500, { form, error: err.message });
		}
	},
};

import { apiFetch } from '$lib/api';
import { modelUpdateSchema } from '$lib/schemas';
import { fail, redirect } from '@sveltejs/kit';
import { superValidate } from 'sveltekit-superforms';
import { zod } from 'sveltekit-superforms/adapters';
import type { PageServerLoad, Actions } from './$types';

export const load: PageServerLoad = async ({ params }) => {
	const model = await apiFetch(`v1/models/${params.id}`);
	const form = await superValidate({
		display_name: model.display_name,
		provider: model.provider,
		provider_model: model.provider_model,
		description: model.description || '',
	}, zod(modelUpdateSchema));
	return { model, form };
};

export const actions: Actions = {
	update: async ({ request, params }) => {
		const form = await superValidate(request, zod(modelUpdateSchema));
		if (!form.valid) {
			return fail(400, { form });
		}

		const payload: Record<string, any> = {};
		if (form.data.display_name !== undefined) payload.display_name = form.data.display_name;
		if (form.data.provider !== undefined) payload.provider = form.data.provider;
		if (form.data.provider_model !== undefined) payload.provider_model = form.data.provider_model;
		if (form.data.description !== undefined) payload.description = form.data.description || null;

		try {
			await apiFetch(`v1/models/${params.id}`, { method: 'PATCH', body: JSON.stringify(payload) });
			throw redirect(303, `/models/${params.id}`);
		} catch (err: any) {
			if (err.status === 303) throw err;
			return fail(500, { form, error: err.message });
		}
	},
	archive: async ({ params }) => {
		try {
			await apiFetch(`v1/models/${params.id}/archive`, { method: 'POST' });
			throw redirect(303, '/models');
		} catch (err: any) {
			if (err.status === 303) throw err;
			return fail(500, { error: err.message });
		}
	}
};

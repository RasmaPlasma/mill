import { apiFetch } from '$lib/api';
import { modelCreateSchema } from '$lib/schemas';
import { fail, redirect } from '@sveltejs/kit';
import { superValidate } from 'sveltekit-superforms';
import { zod } from 'sveltekit-superforms/adapters';
import type { PageServerLoad, Actions } from './$types';

export const load: PageServerLoad = async () => {
	const form = await superValidate(zod(modelCreateSchema));
	return { form };
};

export const actions: Actions = {
	default: async ({ request }) => {
		const form = await superValidate(request, zod(modelCreateSchema));
		if (!form.valid) {
			return fail(400, { form });
		}

		const payload = {
			display_name: form.data.display_name,
			provider: form.data.provider,
			provider_model: form.data.provider_model,
			description: form.data.description || null,
		};

		try {
			await apiFetch('v1/models', { method: 'POST', body: JSON.stringify(payload) });
			throw redirect(303, '/models');
		} catch (err: any) {
			if (err.status === 303) throw err;
			return fail(500, { form, error: err.message });
		}
	}
};

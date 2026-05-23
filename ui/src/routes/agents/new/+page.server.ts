import { apiFetch } from '$lib/api';
import { agentCreateSchema } from '$lib/schemas';
import { fail, redirect } from '@sveltejs/kit';
import { superValidate } from 'sveltekit-superforms';
import { zod } from 'sveltekit-superforms/adapters';
import type { PageServerLoad, Actions } from './$types';

export const load: PageServerLoad = async () => {
	const [form, modelsData] = await Promise.all([
		superValidate(zod(agentCreateSchema)),
		apiFetch('v1/models?limit=100'),
	]);
	return { form, models: modelsData.items ?? [] };
};

export const actions: Actions = {
	default: async ({ request }) => {
		const form = await superValidate(request, zod(agentCreateSchema));
		if (!form.valid) {
			return fail(400, { form });
		}

		const payload = {
			name: form.data.name,
			model_id: form.data.model_id,
			system_prompt: form.data.system_prompt || null,
			description: form.data.description || null,
			tools: form.data.tools ? form.data.tools.split(/[\n,]+/).map((s: string) => s.trim()).filter(Boolean) : [],
			mcp_servers: form.data.mcp_servers_json ? JSON.parse(form.data.mcp_servers_json) : [],
			metadata: form.data.metadata_json ? JSON.parse(form.data.metadata_json) : {},
		};

		try {
			await apiFetch('v1/agents', { method: 'POST', body: JSON.stringify(payload) });
			throw redirect(303, '/agents');
		} catch (err: any) {
			if (err.status === 303) throw err;
			return fail(500, { form, error: err.message });
		}
	}
};

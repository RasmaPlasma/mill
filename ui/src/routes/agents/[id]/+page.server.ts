import { apiFetch } from '$lib/api';
import { agentUpdateSchema } from '$lib/schemas';
import { fail, redirect } from '@sveltejs/kit';
import { superValidate } from 'sveltekit-superforms';
import { zod } from 'sveltekit-superforms/adapters';
import type { PageServerLoad, Actions } from './$types';

export const load: PageServerLoad = async ({ params }) => {
	const [agent, modelsData] = await Promise.all([
		apiFetch(`v1/agents/${params.id}`),
		apiFetch('v1/models?limit=100'),
	]);
	const form = await superValidate({
		name: agent.name,
		model_id: agent.model_id || undefined,
		system_prompt: agent.system_prompt || '',
		description: agent.description || '',
		tools: (agent.tools || []).join('\n'),
		mcp_servers_json: JSON.stringify(agent.mcp_servers || [], null, 2),
		metadata_json: JSON.stringify(agent.metadata || {}, null, 2),
	}, zod(agentUpdateSchema));
	return { agent, form, models: modelsData.items ?? [] };
};

export const actions: Actions = {
	update: async ({ request, params }) => {
		const form = await superValidate(request, zod(agentUpdateSchema));
		if (!form.valid) {
			return fail(400, { form });
		}

		const payload: Record<string, any> = {};
		if (form.data.name !== undefined) payload.name = form.data.name;
		if (form.data.model_id !== undefined) payload.model_id = form.data.model_id || null;
		if (form.data.system_prompt !== undefined) payload.system_prompt = form.data.system_prompt || null;
		if (form.data.description !== undefined) payload.description = form.data.description || null;
		if (form.data.tools !== undefined) payload.tools = form.data.tools ? form.data.tools.split(/[\n,]+/).map((s: string) => s.trim()).filter(Boolean) : [];
		if (form.data.mcp_servers_json !== undefined) payload.mcp_servers = form.data.mcp_servers_json ? JSON.parse(form.data.mcp_servers_json) : [];
		if (form.data.metadata_json !== undefined) payload.metadata = form.data.metadata_json ? JSON.parse(form.data.metadata_json) : {};

		try {
			await apiFetch(`v1/agents/${params.id}`, { method: 'PATCH', body: JSON.stringify(payload) });
			throw redirect(303, `/agents/${params.id}`);
		} catch (err: any) {
			if (err.status === 303) throw err;
			return fail(500, { form, error: err.message });
		}
	},
	archive: async ({ params }) => {
		try {
			await apiFetch(`v1/agents/${params.id}/archive`, { method: 'POST' });
			throw redirect(303, '/agents');
		} catch (err: any) {
			if (err.status === 303) throw err;
			return fail(500, { error: err.message });
		}
	}
};

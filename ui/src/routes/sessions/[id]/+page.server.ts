import { apiFetch } from '$lib/api';
import { sessionEventSchema } from '$lib/schemas';
import { fail, redirect } from '@sveltejs/kit';
import { superValidate } from 'sveltekit-superforms';
import { zod } from 'sveltekit-superforms/adapters';
import type { PageServerLoad, Actions } from './$types';

export const load: PageServerLoad = async ({ params }) => {
	const session = await apiFetch(`v1/sessions/${params.id}`);

	// Fetch full agent details
	let agentDetails: any = null;
	if (session.agent_id) {
		try {
			agentDetails = await apiFetch(`v1/agents/${session.agent_id}`);
		} catch {
			// ignore
		}
	}

	// Fetch full environment details
	let envDetails: any = null;
	if (session.environment_id) {
		try {
			envDetails = await apiFetch(`v1/environments/${session.environment_id}`);
		} catch {
			// ignore
		}
	}

	let vaultNames: Record<string, string> = {};
	if (session.vault_ids?.length) {
		try {
			const vaultsData = await apiFetch('v1/vaults?limit=100');
			for (const v of vaultsData.items ?? []) {
				vaultNames[v.id] = v.display_name;
			}
		} catch {
			// ignore
		}
	}

	// Load recent events for initial render
	let events: any[] = [];
	let eventsCount = 0;
	try {
		const eventsData = await apiFetch(`v1/sessions/${params.id}/events?limit=200&order=asc`);
		events = eventsData.items ?? [];
		eventsCount = eventsData.count ?? 0;
	} catch {
		// ignore — will load via SSE or client-side fetch
	}

	const form = await superValidate(zod(sessionEventSchema));

	return { session, agentDetails, envDetails, vaultNames, form, events, eventsCount };
};

export const actions: Actions = {
	archive: async ({ params }) => {
		try {
			await apiFetch(`v1/sessions/${params.id}/archive`, { method: 'POST' });
			throw redirect(303, '/sessions');
		} catch (err: any) {
			if (err.status === 303) throw err;
			return fail(500, { error: err.message });
		}
	},
	interrupt: async ({ params }) => {
		try {
			const res = await apiFetch(`v1/sessions/${params.id}/interrupt`, { method: 'POST' });
			return { success: true, status: res.status };
		} catch (err: any) {
			return fail(500, { error: err.message });
		}
	},
	sendEvent: async ({ params, request }) => {
		const form = await superValidate(request, zod(sessionEventSchema));
		if (!form.valid) {
			return fail(400, { form });
		}

		const payload = {
			events: [
				{
					type: 'user.message',
					content: [{ type: 'text', text: form.data.message }],
				},
			],
		};

		try {
			const res = await apiFetch(`v1/sessions/${params.id}/events`, {
				method: 'POST',
				body: JSON.stringify(payload),
			});
			return { success: true, run_id: res.run_id, thread_id: res.thread_id, form };
		} catch (err: any) {
			return fail(500, { form, error: err.message });
		}
	},
};

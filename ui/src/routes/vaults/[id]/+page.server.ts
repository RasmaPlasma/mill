import { apiFetch } from '$lib/api';
import { vaultCreateSchema, credentialCreateSchema, credentialRotateSchema } from '$lib/schemas';
import { fail, redirect } from '@sveltejs/kit';
import { superValidate } from 'sveltekit-superforms';
import { zod } from 'sveltekit-superforms/adapters';
import type { PageServerLoad, Actions } from './$types';

export const load: PageServerLoad = async ({ params }) => {
	const vault = await apiFetch(`v1/vaults/${params.id}`);
	const form = await superValidate(zod(vaultCreateSchema));
	// Pre-populate for edit tab
	form.data.display_name = vault.display_name ?? '';
	form.data.metadata_json = JSON.stringify(vault.metadata || {}, null, 2);
	return { vault, form };
};

export const actions: Actions = {
	update: async ({ params, request }) => {
		const form = await superValidate(request, zod(vaultCreateSchema));
		if (!form.valid) {
			return fail(400, { form });
		}
		const payload: Record<string, any> = {};
		if (form.data.display_name !== undefined) payload.display_name = form.data.display_name;
		if (form.data.metadata_json !== undefined) payload.metadata = form.data.metadata_json ? JSON.parse(form.data.metadata_json) : {};

		try {
			await apiFetch(`v1/vaults/${params.id}`, {
				method: 'PATCH',
				body: JSON.stringify(payload),
			});
		} catch (err: any) {
			return fail(400, { form, error: err.message });
		}
		throw redirect(303, `/vaults/${params.id}`);
	},
	archive: async ({ params }) => {
		try {
			await apiFetch(`v1/vaults/${params.id}/archive`, { method: 'POST' });
			throw redirect(303, '/vaults');
		} catch (err: any) {
			if (err.status === 303) throw err;
			return fail(500, { error: err.message });
		}
	},
	createCredential: async ({ params, request }) => {
		const form = await superValidate(request, zod(credentialCreateSchema));
		if (!form.valid) {
			return fail(400, { form });
		}
		const payload = {
			display_name: form.data.display_name,
			mcp_server_url: form.data.mcp_server_url,
			auth_type: form.data.auth_type,
			token: form.data.token,
			refresh_token: form.data.refresh_token || undefined,
			token_endpoint: form.data.token_endpoint || undefined,
			client_id: form.data.client_id || undefined,
			scope: form.data.scope || undefined,
			expires_at: form.data.expires_at || undefined,
		};
		try {
			const res = await apiFetch(`v1/vaults/${params.id}/credentials`, {
				method: 'POST',
				body: JSON.stringify(payload),
			});
			return { success: true, credential: res };
		} catch (err: any) {
			return fail(500, { form, error: err.message });
		}
	},
	rotateCredential: async ({ params, request }) => {
		const form = await superValidate(request, zod(credentialRotateSchema));
		if (!form.valid) {
			return fail(400, { form });
		}
		const payload: Record<string, any> = {
			token: form.data.token,
		};
		if (form.data.refresh_token !== undefined) payload.refresh_token = form.data.refresh_token || undefined;
		if (form.data.expires_at !== undefined) payload.expires_at = form.data.expires_at || undefined;

		try {
			const res = await apiFetch(`v1/vaults/${params.id}/credentials/${form.data.credential_id}`, {
				method: 'PATCH',
				body: JSON.stringify(payload),
			});
			return { success: true, credential: res };
		} catch (err: any) {
			return fail(500, { form, error: err.message });
		}
	},
};

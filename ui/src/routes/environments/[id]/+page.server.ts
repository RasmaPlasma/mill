import { apiFetch } from '$lib/api';
import { environmentUpdateSchema } from '$lib/schemas';
import { fail, redirect } from '@sveltejs/kit';
import { superValidate } from 'sveltekit-superforms';
import { zod } from 'sveltekit-superforms/adapters';
import type { PageServerLoad, Actions } from './$types';

export const load: PageServerLoad = async ({ params }) => {
	const env = await apiFetch(`v1/environments/${params.id}`);
	const form = await superValidate(zod(environmentUpdateSchema));
	// Pre-populate form fields for edit tab
	form.data.name = env.name ?? '';
	form.data.base_image = env.base_image ?? '';
	form.data.packages_pip = (env.packages?.pip ?? []).join(' ');
	form.data.packages_npm = (env.packages?.npm ?? []).join(' ');
	form.data.packages_apt = (env.packages?.apt ?? []).join(' ');
	form.data.networking_type = env.networking?.type ?? 'limited';
	form.data.networking_allowed_hosts = (env.networking?.allowed_hosts ?? []).join(' ');
	form.data.networking_allow_package_managers = env.networking?.allow_package_managers ?? false;
	form.data.resource_memory = env.resource_limits?.memory ?? '1g';
	form.data.resource_cpus = env.resource_limits?.cpus ?? 1;
	form.data.resource_pids_limit = env.resource_limits?.pids_limit ?? 256;
	form.data.skill_repos_json = JSON.stringify(env.skill_repos ?? [], null, 2);
	form.data.repositories_json = JSON.stringify(env.repositories ?? [], null, 2);
	return { env, form };
};

export const actions: Actions = {
	update: async ({ params, request }) => {
		const form = await superValidate(request, zod(environmentUpdateSchema));
		if (!form.valid) {
			return fail(400, { form });
		}

		const body: Record<string, any> = {};
		if (form.data.name !== undefined) body.name = form.data.name;
		if (form.data.base_image !== undefined) body.base_image = form.data.base_image || null;

		if (form.data.packages_pip !== undefined || form.data.packages_npm !== undefined || form.data.packages_apt !== undefined) {
			body.packages = {};
			if (form.data.packages_pip) body.packages.pip = form.data.packages_pip.split(/\s*,\s*|\s+/).filter(Boolean);
			if (form.data.packages_npm) body.packages.npm = form.data.packages_npm.split(/\s*,\s*|\s+/).filter(Boolean);
			if (form.data.packages_apt) body.packages.apt = form.data.packages_apt.split(/\s*,\s*|\s+/).filter(Boolean);
		}

		if (form.data.networking_type !== undefined || form.data.networking_allowed_hosts !== undefined || form.data.networking_allow_package_managers !== undefined) {
			body.networking = {
				type: form.data.networking_type ?? 'limited',
				allowed_hosts: form.data.networking_allowed_hosts
					? form.data.networking_allowed_hosts.split(/\s*,\s*|\s+/).filter(Boolean)
					: [],
				allow_package_managers: form.data.networking_allow_package_managers ?? false,
			};
		}

		if (form.data.resource_memory !== undefined || form.data.resource_cpus !== undefined || form.data.resource_pids_limit !== undefined) {
			body.resource_limits = {
				memory: form.data.resource_memory ?? '1g',
				cpus: form.data.resource_cpus ?? 1,
				pids_limit: form.data.resource_pids_limit ?? 256,
			};
		}

		if (form.data.skill_repos_json !== undefined) {
			body.skill_repos = form.data.skill_repos_json ? JSON.parse(form.data.skill_repos_json) : [];
		}

		if (form.data.repositories_json !== undefined) {
			body.repositories = form.data.repositories_json ? JSON.parse(form.data.repositories_json) : [];
		}

		try {
			await apiFetch(`v1/environments/${params.id}`, {
				method: 'PATCH',
				body: JSON.stringify(body),
			});
		} catch (err: any) {
			return fail(400, { form, error: err.message });
		}
		throw redirect(303, `/environments/${params.id}`);
	},
	archive: async ({ params }) => {
		try {
			await apiFetch(`v1/environments/${params.id}/archive`, { method: 'POST' });
			throw redirect(303, '/environments');
		} catch (err: any) {
			if (err.status === 303) throw err;
			return fail(500, { error: err.message });
		}
	}
};

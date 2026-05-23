import { apiFetch } from '$lib/api';
import { environmentCreateSchema } from '$lib/schemas';
import { fail, redirect } from '@sveltejs/kit';
import { superValidate } from 'sveltekit-superforms';
import { zod } from 'sveltekit-superforms/adapters';
import type { PageServerLoad, Actions } from './$types';

export const load: PageServerLoad = async () => {
	const form = await superValidate(zod(environmentCreateSchema));
	return { form };
};

export const actions: Actions = {
	default: async ({ request }) => {
		const form = await superValidate(request, zod(environmentCreateSchema));
		if (!form.valid) {
			return fail(400, { form });
		}

		const packages: Record<string, string[]> = {};
		if (form.data.packages_pip) packages.pip = form.data.packages_pip.split(/\s*,\s*|\s+/).filter(Boolean);
		if (form.data.packages_npm) packages.npm = form.data.packages_npm.split(/\s*,\s*|\s+/).filter(Boolean);
		if (form.data.packages_apt) packages.apt = form.data.packages_apt.split(/\s*,\s*|\s+/).filter(Boolean);

		const networking = {
			type: form.data.networking_type,
			allowed_hosts: form.data.networking_allowed_hosts
				? form.data.networking_allowed_hosts.split(/\s*,\s*|\s+/).filter(Boolean)
				: [],
			allow_package_managers: form.data.networking_allow_package_managers,
		};

		const resource_limits = {
			memory: form.data.resource_memory,
			cpus: form.data.resource_cpus,
			pids_limit: form.data.resource_pids_limit,
		};

		const skill_repos = form.data.skill_repos_json
			? JSON.parse(form.data.skill_repos_json)
			: [];

		const repositories = form.data.repositories_json
			? JSON.parse(form.data.repositories_json)
			: [];

		try {
			await apiFetch('v1/environments', {
				method: 'POST',
				body: JSON.stringify({
					name: form.data.name,
					base_image: form.data.base_image || undefined,
					packages,
					networking,
					resource_limits,
					skill_repos,
					repositories,
				}),
			});
		} catch (err: any) {
			return fail(400, { form, error: err.message });
		}
		throw redirect(303, '/environments');
	}
};

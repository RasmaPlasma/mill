import { apiFetch } from '$lib/api';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async () => {
	const [agents, envs, sessions, vaults] = await Promise.all([
		apiFetch('v1/agents').catch(() => ({ count: 0 })),
		apiFetch('v1/environments').catch(() => ({ count: 0 })),
		apiFetch('v1/sessions').catch(() => ({ count: 0 })),
		apiFetch('v1/vaults').catch(() => ({ count: 0 })),
	]);

	return {
		counts: {
			agents: agents.count ?? 0,
			environments: envs.count ?? 0,
			sessions: sessions.count ?? 0,
			vaults: vaults.count ?? 0,
		}
	};
};

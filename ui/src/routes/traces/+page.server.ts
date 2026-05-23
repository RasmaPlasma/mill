import { env } from '$env/dynamic/private';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async () => {
	return {
		phoenixUrl: env.PHOENIX_URL || 'http://localhost:6006',
	};
};

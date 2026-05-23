import { env } from '$env/dynamic/private';
import { betterAuth } from 'better-auth';
import { sveltekitCookies } from 'better-auth/svelte-kit';
import { getRequestEvent } from '$app/server';
import { Pool } from 'pg';

const dbUrl = env.DATABASE_URL || 'postgresql://postgres:postgres@localhost:5432/postgres';

export const auth = betterAuth({
	database: new Pool({ connectionString: dbUrl }),
	secret: env.BETTER_AUTH_SECRET || 'dev-secret-change-me',
	baseURL: env.ORIGIN || 'http://localhost:5173',
	emailAndPassword: {
		enabled: true,
		autoSignIn: true,
	},
	plugins: [sveltekitCookies(getRequestEvent)],
});

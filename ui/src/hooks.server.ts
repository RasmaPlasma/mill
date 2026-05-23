import { auth } from '$lib/auth';
import { svelteKitHandler } from 'better-auth/svelte-kit';
import { building } from '$app/environment';
import { redirect } from '@sveltejs/kit';

const PROTECTED_PREFIXES = ['/agents', '/models', '/environments', '/sessions', '/vaults', '/secrets', '/traces'];

function isProtected(pathname: string): boolean {
	if (pathname === '/') return true;
	if (pathname.startsWith('/login')) return false;
	if (pathname.startsWith('/api/auth')) return false;
	return PROTECTED_PREFIXES.some((p) => pathname.startsWith(p));
}

export const handle = async ({ event, resolve }) => {
	// Populate session data BEFORE svelteKitHandler runs
	const session = await auth.api.getSession({ headers: event.request.headers });
	event.locals.user = session?.user ?? null;
	event.locals.session = session?.session ?? null;

	// Redirect unauthenticated users away from protected routes
	if (!event.locals.user && isProtected(event.url.pathname)) {
		throw redirect(303, '/login');
	}

	// Auth routes are handled by svelteKitHandler internally
	// For non-auth routes, it just resolves normally
	return svelteKitHandler({ event, resolve, auth, building });
};

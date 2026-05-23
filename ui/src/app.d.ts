/// <reference types="@sveltejs/kit" />

declare module '@fontsource-variable/inter' {}
declare module '@fontsource/instrument-serif' {}

declare global {
	namespace App {
		interface Locals {
			user: {
				id: string;
				email: string;
				emailVerified: boolean;
				name: string;
				image?: string | null;
				createdAt: Date;
				updatedAt: Date;
			} | null;
			session: {
				id: string;
				userId: string;
				expiresAt: Date;
			} | null;
		}
		interface PageData {
			user?: App.Locals['user'];
		}
	}
}

export {};

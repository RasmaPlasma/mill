<script lang="ts">
	import { goto } from '$app/navigation';
	import { Button } from '$lib/components/ui/button';
	import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import { Tabs, TabsContent, TabsList, TabsTrigger } from '$lib/components/ui/tabs';
	import { toast } from 'svelte-sonner';
	import Logo from '$lib/components/logo.svelte';

	let email = $state('');
	let password = $state('');
	let name = $state('');
	let loading = $state(false);

	async function signIn(e: Event) {
		e.preventDefault();
		loading = true;
		try {
			const res = await fetch('/api/auth/sign-in/email', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ email, password })
			});
			if (!res.ok) {
				const data = await res.json().catch(() => ({}));
				throw new Error(data.message || 'Invalid credentials');
			}
			toast.success('Signed in successfully');
			goto('/');
		} catch (err: any) {
			toast.error(err.message || 'Failed to sign in');
		} finally {
			loading = false;
		}
	}

	async function signUp(e: Event) {
		e.preventDefault();
		loading = true;
		try {
			const res = await fetch('/api/auth/sign-up/email', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ email, password, name })
			});
			if (!res.ok) {
				const data = await res.json().catch(() => ({}));
				throw new Error(data.message || 'Failed to create account');
			}
			toast.success('Account created successfully');
			goto('/');
		} catch (err: any) {
			toast.error(err.message || 'Failed to sign up');
		} finally {
			loading = false;
		}
	}
</script>

<div class="flex min-h-screen items-center justify-center bg-muted/40 p-4">
	<Card class="w-full max-w-md">
		<CardHeader class="text-center">
			<div class="flex justify-center mb-4">
				<Logo class="text-3xl" />
			</div>
			<CardDescription>Sign in to your admin panel</CardDescription>
		</CardHeader>
		<CardContent>
			<Tabs value="signin" class="w-full">
				<TabsList class="grid w-full grid-cols-2">
					<TabsTrigger value="signin">Sign In</TabsTrigger>
					<TabsTrigger value="signup">Sign Up</TabsTrigger>
				</TabsList>
				<TabsContent value="signin">
					<form onsubmit={signIn} class="space-y-4 mt-4">
						<div class="space-y-2">
							<Label for="signin-email">Email</Label>
							<Input id="signin-email" type="email" bind:value={email} required />
						</div>
						<div class="space-y-2">
							<Label for="signin-password">Password</Label>
							<Input id="signin-password" type="password" bind:value={password} required />
						</div>
						<Button type="submit" class="w-full" disabled={loading}>
							{loading ? 'Signing in...' : 'Sign In'}
						</Button>
					</form>
				</TabsContent>
				<TabsContent value="signup">
					<form onsubmit={signUp} class="space-y-4 mt-4">
						<div class="space-y-2">
							<Label for="signup-name">Name</Label>
							<Input id="signup-name" bind:value={name} />
						</div>
						<div class="space-y-2">
							<Label for="signup-email">Email</Label>
							<Input id="signup-email" type="email" bind:value={email} required />
						</div>
						<div class="space-y-2">
							<Label for="signup-password">Password</Label>
							<Input id="signup-password" type="password" bind:value={password} required minlength={8} />
						</div>
						<Button type="submit" class="w-full" disabled={loading}>
							{loading ? 'Creating account...' : 'Create Account'}
						</Button>
					</form>
				</TabsContent>
			</Tabs>
		</CardContent>
	</Card>
</div>

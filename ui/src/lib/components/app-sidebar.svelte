<script lang="ts">
	import { page } from '$app/stores';
	import { Button } from '$lib/components/ui/button';
	import {
		Bot,
		Container,
		Home,
		Key,
		Lock,
		Play,
		Activity,
		Cpu,
		Sun,
		Moon,
		Monitor
	} from 'lucide-svelte';
	import Logo from '$lib/components/logo.svelte';
	import { setMode } from 'mode-watcher';
	import {
		DropdownMenu,
		DropdownMenuContent,
		DropdownMenuItem,
		DropdownMenuLabel,
		DropdownMenuSeparator,
		DropdownMenuTrigger
	} from '$lib/components/ui/dropdown-menu';

	const navItems = [
		{ href: '/', label: 'Dashboard', icon: Home },
		{ href: '/agents', label: 'Agents', icon: Bot },
		{ href: '/models', label: 'Models', icon: Cpu },
		{ href: '/environments', label: 'Environments', icon: Container },
		{ href: '/sessions', label: 'Sessions', icon: Play },
		{ href: '/vaults', label: 'Vaults', icon: Lock },
		{ href: '/secrets', label: 'Secrets', icon: Key },
		{ href: '/traces', label: 'Traces', icon: Activity },
	];
</script>

<aside class="hidden lg:flex flex-col w-60 border-r bg-background h-screen sticky top-0">
	<div class="flex items-center gap-2 px-4 h-14 border-b">
		<Logo />
	</div>
	<nav class="flex-1 overflow-auto py-4 px-3 space-y-1">
		{#each navItems as item}
			{@const isActive = $page.url.pathname === item.href || $page.url.pathname.startsWith(item.href + '/')}
			<a
				href={item.href}
				class="flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors {isActive ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'}"
			>
				<item.icon class="h-4 w-4" />
				{item.label}
			</a>
		{/each}
	</nav>
	<div class="border-t p-4 flex items-center gap-2">
		<form action="/api/auth/signout" method="POST" class="flex-1">
			<Button type="submit" variant="ghost" class="w-full justify-start text-muted-foreground">
				Sign out
			</Button>
		</form>
		<DropdownMenu>
			<DropdownMenuTrigger>
				{#snippet child({ props })}
					<Button {...props} variant="ghost" size="icon" class="relative shrink-0">
						<Sun class="h-5 w-5 rotate-0 scale-100 transition-all dark:-rotate-90 dark:scale-0" />
						<Moon class="absolute h-5 w-5 rotate-90 scale-0 transition-all dark:rotate-0 dark:scale-100" />
						<span class="sr-only">Toggle theme</span>
					</Button>
				{/snippet}
			</DropdownMenuTrigger>
			<DropdownMenuContent align="end">
				<DropdownMenuLabel>Theme</DropdownMenuLabel>
				<DropdownMenuSeparator />
				<DropdownMenuItem onclick={() => setMode('light')}>
					<Sun class="mr-2 h-4 w-4" />
					<span>Light</span>
				</DropdownMenuItem>
				<DropdownMenuItem onclick={() => setMode('dark')}>
					<Moon class="mr-2 h-4 w-4" />
					<span>Dark</span>
				</DropdownMenuItem>
				<DropdownMenuItem onclick={() => setMode('system')}>
					<Monitor class="mr-2 h-4 w-4" />
					<span>System</span>
				</DropdownMenuItem>
			</DropdownMenuContent>
		</DropdownMenu>
	</div>
</aside>

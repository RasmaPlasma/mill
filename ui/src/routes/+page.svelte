<script lang="ts">
	import { Button } from '$lib/components/ui/button';
	import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Bot, Container, Play, Lock, ArrowRight } from 'lucide-svelte';

	let { data } = $props();

	let stats = $derived([
		{ label: 'Agents', count: data.counts.agents, href: '/agents', icon: Bot, color: 'text-chart-1' },
		{ label: 'Environments', count: data.counts.environments, href: '/environments', icon: Container, color: 'text-chart-2' },
		{ label: 'Sessions', count: data.counts.sessions, href: '/sessions', icon: Play, color: 'text-chart-4' },
		{ label: 'Vaults', count: data.counts.vaults, href: '/vaults', icon: Lock, color: 'text-chart-5' },
	]);
</script>

<div class="space-y-6">
	<div>
		<h2 class="text-2xl font-bold tracking-tight">Dashboard</h2>
		<p class="text-muted-foreground">Overview of your Mill platform.</p>
	</div>

	<div class="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
		{#each stats as stat}
			<Card>
				<CardHeader class="flex flex-row items-center justify-between pb-2">
					<CardTitle class="text-sm font-medium">{stat.label}</CardTitle>
					<stat.icon class="h-4 w-4 {stat.color}" />
				</CardHeader>
				<CardContent>
					<div class="text-3xl font-bold">{stat.count}</div>
					<Button variant="link" class="px-0" href={stat.href}>
						View all <ArrowRight class="ml-1 h-3 w-3" />
					</Button>
				</CardContent>
			</Card>
		{/each}
	</div>
</div>

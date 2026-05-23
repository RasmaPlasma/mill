<script lang="ts">
	import ResourceList from '$lib/components/resource-list.svelte';
	import { Badge } from '$lib/components/ui/badge';
	import { TableCell, TableHead } from '$lib/components/ui/table';

	let { data } = $props();

	function packageSummary(packages: Record<string, string[]>) {
		const counts: string[] = [];
		if (packages?.pip?.length) counts.push(`${packages.pip.length} pip`);
		if (packages?.npm?.length) counts.push(`${packages.npm.length} npm`);
		if (packages?.apt?.length) counts.push(`${packages.apt.length} apt`);
		return counts.length ? counts.join(', ') : '-';
	}
</script>

<ResourceList
	items={data.environments}
	count={data.count}
	limit={data.limit}
	offset={data.offset}
	title="Environments"
	description="Manage sandbox environments."
	detailHref={(env: any) => `/environments/${env.id}`}
	archiveAction="?/bulkArchive"
	archiveToast="Environments archived"
	createHref="/environments/new"
	emptyCreateHref="/environments/new"
>
	{#snippet tableHead()}
		<TableHead>Name</TableHead>
		<TableHead>Packages</TableHead>
		<TableHead>Networking</TableHead>
		<TableHead>Resources</TableHead>
		<TableHead>Created</TableHead>
	{/snippet}

	{#snippet tableRow(env: any)}
		<TableCell class="font-medium">
			<a href="/environments/{env.id}" class="hover:underline">{env.name}</a>
		</TableCell>
		<TableCell class="text-muted-foreground">
			{packageSummary(env.packages)}
		</TableCell>
		<TableCell>
			<Badge variant="outline">{env.networking?.type || 'limited'}</Badge>
		</TableCell>
		<TableCell class="text-muted-foreground text-sm">
			{env.resource_limits?.memory || '-'} / {env.resource_limits?.cpus || '-'} CPU
		</TableCell>
		<TableCell class="text-muted-foreground">
			{env.created_at ? new Date(env.created_at).toLocaleDateString() : '-'}
		</TableCell>
	{/snippet}
</ResourceList>

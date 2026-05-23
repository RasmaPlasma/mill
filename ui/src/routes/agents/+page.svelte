<script lang="ts">
	import ResourceList from '$lib/components/resource-list.svelte';
	import { Badge } from '$lib/components/ui/badge';
	import { TableCell, TableHead } from '$lib/components/ui/table';

	let { data } = $props();
</script>

<ResourceList
	items={data.agents}
	count={data.count}
	limit={data.limit}
	offset={data.offset}
	title="Agents"
	description="Manage your agent configurations."
	detailHref={(agent: any) => `/agents/${agent.id}`}
	archiveAction="?/bulkArchive"
	archiveToast="Agents archived"
	createHref="/agents/new"
	emptyCreateHref="/agents/new"
>
	{#snippet tableHead()}
		<TableHead>Name</TableHead>
		<TableHead>Model</TableHead>
		<TableHead>Description</TableHead>
		<TableHead>Version</TableHead>
		<TableHead>Created</TableHead>
	{/snippet}

	{#snippet tableRow(agent: any)}
		<TableCell class="font-medium">
			<a href="/agents/{agent.id}" class="hover:underline">{agent.name}</a>
		</TableCell>
		<TableCell>
			<Badge variant="outline" class="max-w-[200px]">
				<span class="truncate" title={agent.model}>{agent.model}</span>
			</Badge>
		</TableCell>
		<TableCell class="text-muted-foreground max-w-[240px] truncate">
			{agent.description || '-'}
		</TableCell>
		<TableCell>
			<Badge variant="secondary">v{agent.version}</Badge>
		</TableCell>
		<TableCell class="text-muted-foreground">
			{agent.created_at ? new Date(agent.created_at).toLocaleDateString() : '-'}
		</TableCell>
	{/snippet}
</ResourceList>

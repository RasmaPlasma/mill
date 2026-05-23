<script lang="ts">
	import ResourceList from '$lib/components/resource-list.svelte';
	import { Badge } from '$lib/components/ui/badge';
	import { TableCell, TableHead } from '$lib/components/ui/table';

	let { data } = $props();
</script>

<ResourceList
	items={data.models}
	count={data.count}
	limit={data.limit}
	offset={data.offset}
	title="Models"
	description="Manage configured LLM models."
	detailHref={(model: any) => `/models/${model.id}`}
	archiveAction="?/bulkArchive"
	archiveToast="Models archived"
	createHref="/models/new"
	emptyCreateHref="/models/new"
>
	{#snippet tableHead()}
		<TableHead>Name</TableHead>
		<TableHead>Provider</TableHead>
		<TableHead>Model ID</TableHead>
	{/snippet}

	{#snippet tableRow(model: any)}
		<TableCell class="font-medium">
			<a href="/models/{model.id}" class="hover:underline">{model.display_name}</a>
		</TableCell>
		<TableCell>
			<Badge variant="secondary">{model.provider}</Badge>
		</TableCell>
		<TableCell class="text-muted-foreground max-w-[300px] truncate">
			{model.provider_model}
		</TableCell>
	{/snippet}
</ResourceList>

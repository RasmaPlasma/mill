<script lang="ts">
	import { invalidateAll } from '$app/navigation';
	import { superForm } from 'sveltekit-superforms';
	import ResourceList from '$lib/components/resource-list.svelte';
	import { Button } from '$lib/components/ui/button';
	import { TableCell, TableHead } from '$lib/components/ui/table';
	import {
		Dialog,
		DialogContent,
		DialogHeader,
		DialogTitle,
		DialogDescription,
		DialogFooter,
	} from '$lib/components/ui/dialog';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import { Textarea } from '$lib/components/ui/textarea';
	import { toast } from 'svelte-sonner';
	import { Plus, Loader2 } from 'lucide-svelte';

	let { data } = $props();
	let createOpen = $state(false);

	const { form, errors, enhance, submitting, delayed } = superForm(data.form, {
		applyAction: false,
		invalidateAll: false,
		onResult: ({ result }) => {
			if (result.type === 'success') {
				createOpen = false;
				toast.success('Vault created');
				invalidateAll();
			}
			if (result.type === 'failure') {
				const err = result.data?.error;
				if (err) toast.error(err);
			}
		},
	});

	function metadataSummary(vault: any) {
		const keys = Object.keys(vault.metadata || {});
		return keys.length ? `${keys.length} keys` : '-';
	}
</script>

<ResourceList
	items={data.vaults}
	count={data.count}
	limit={data.limit}
	offset={data.offset}
	title="Vaults"
	description="Manage MCP credential vaults."
	detailHref={(vault: any) => `/vaults/${vault.id}`}
	archiveAction="?/bulkArchive"
	archiveToast="Vaults archived"
>
	{#snippet createButton()}
		<Button onclick={() => (createOpen = true)}>
			<Plus class="mr-2 h-4 w-4" />
			Create Vault
		</Button>
	{/snippet}

	{#snippet emptyCreateButton()}
		<button class="underline" onclick={() => (createOpen = true)}>Create your first vault</button>.
	{/snippet}

	{#snippet tableHead()}
		<TableHead>Display Name</TableHead>
		<TableHead>Metadata</TableHead>
		<TableHead>Created</TableHead>
	{/snippet}

	{#snippet tableRow(vault: any)}
		<TableCell class="font-medium">
			<a href="/vaults/{vault.id}" class="hover:underline">{vault.display_name}</a>
		</TableCell>
		<TableCell class="text-muted-foreground">
			{metadataSummary(vault)}
		</TableCell>
		<TableCell class="text-muted-foreground">
			{vault.created_at ? new Date(vault.created_at).toLocaleDateString() : '-'}
		</TableCell>
	{/snippet}
</ResourceList>

<Dialog bind:open={createOpen}>
	<DialogContent class="sm:max-w-md">
		<DialogHeader>
			<DialogTitle>Create Vault</DialogTitle>
			<DialogDescription>Create a new credential vault.</DialogDescription>
		</DialogHeader>
		<form method="POST" action="?/create" use:enhance class="space-y-4 py-2">
			<div class="space-y-2">
				<Label for="display_name">Display Name</Label>
				<Input id="display_name" name="display_name" bind:value={$form.display_name} />
				{#if $errors.display_name}<p class="text-sm text-destructive">{$errors.display_name}</p>{/if}
			</div>
			<div class="space-y-2">
				<Label for="metadata_json">Metadata (JSON)</Label>
				<Textarea id="metadata_json" name="metadata_json" bind:value={$form.metadata_json as string} rows={4} placeholder={`{\n  "key": "value"\n}`} />
			</div>
			<DialogFooter>
				<Button type="button" variant="ghost" onclick={() => (createOpen = false)}>Cancel</Button>
				<Button type="submit" disabled={$submitting || $delayed}>
					{#if $submitting || $delayed}
						<Loader2 class="mr-2 h-4 w-4 animate-spin" />
						Creating...
					{:else}
						Create Vault
					{/if}
				</Button>
			</DialogFooter>
		</form>
	</DialogContent>
</Dialog>

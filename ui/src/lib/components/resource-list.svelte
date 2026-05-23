<script lang="ts" generics="T extends Record<string, any>">
	import { invalidateAll } from '$app/navigation';
	import { Button } from '$lib/components/ui/button';
	import { Checkbox } from '$lib/components/ui/checkbox';
	import {
		Card,
		CardContent,
		CardDescription,
		CardHeader,
		CardTitle,
	} from '$lib/components/ui/card';
	import {
		Table,
		TableBody,
		TableCell,
		TableHead,
		TableHeader,
		TableRow,
	} from '$lib/components/ui/table';
	import {
		DropdownMenu,
		DropdownMenuContent,
		DropdownMenuItem,
		DropdownMenuTrigger,
	} from '$lib/components/ui/dropdown-menu';
	import { toast } from 'svelte-sonner';
	import { Plus, Loader2, X, Archive, MoreHorizontal } from 'lucide-svelte';
	import type { Snippet } from 'svelte';

	// ── Props ────────────────────────────────────────────────────────────
	let {
		items,
		count,
		limit,
		offset,
		title,
		description,
		detailHref,
		archiveAction,
		archiveToast,
		idKey = 'id',
		createHref,
		createButton,
		filterSlot,
		emptyCreateHref,
		emptyCreateButton,
		tableHead,
		tableRow,
		extraParams = '',
	}: {
		items: T[];
		count: number;
		limit: number;
		offset: number;
		title: string;
		description: string;
		detailHref: (item: T) => string;
		archiveAction: string;
		archiveToast: string;
		idKey?: string;
		createHref?: string;
		createButton?: Snippet;
		filterSlot?: Snippet;
		emptyCreateHref?: string;
		emptyCreateButton?: Snippet;
		tableHead: Snippet;
		tableRow: Snippet<[T]>;
		extraParams?: string;
	} = $props();

	// ── State ────────────────────────────────────────────────────────────
	let selectedIds = $state<Set<string>>(new Set());
	let archiving = $state(false);

	let totalPages = $derived(Math.ceil(count / limit));
	let currentPage = $derived(Math.floor(offset / limit) + 1);
	let allSelected = $derived(items.length > 0 && items.every((i) => selectedIds.has(i[idKey])));
	let someSelected = $derived(items.some((i) => selectedIds.has(i[idKey])) && !allSelected);
	let selectedCount = $derived(selectedIds.size);

	function toggleSelect(id: string) {
		const next = new Set(selectedIds);
		if (next.has(id)) next.delete(id);
		else next.add(id);
		selectedIds = next;
	}

	function toggleSelectAll() {
		if (allSelected) {
			selectedIds = new Set();
		} else {
			selectedIds = new Set(items.map((i) => i[idKey]));
		}
	}

	function clearSelection() {
		selectedIds = new Set();
	}

	async function bulkArchive() {
		if (selectedCount === 0) return;
		archiving = true;
		const ids = Array.from(selectedIds);
		const fd = new FormData();
		fd.append('ids', JSON.stringify(ids));
		try {
			const res = await fetch(archiveAction, { method: 'POST', body: fd });
			if (!res.ok) {
				const err = await res.json();
				throw new Error(err.error || 'Archive failed');
			}
			toast.success(archiveToast);
			selectedIds = new Set();
			invalidateAll();
		} catch (err: any) {
			toast.error(err.message);
		} finally {
			archiving = false;
		}
	}

	function formatDate(d: string | null) {
		if (!d) return '-';
		return new Date(d).toLocaleDateString();
	}
</script>

<div class="space-y-4">
	<div class="flex items-center justify-between">
		<div>
			<h2 class="text-2xl font-bold tracking-tight">{title}</h2>
			<p class="text-muted-foreground">{description}</p>
		</div>
		{#if createHref}
			<Button href={createHref}>
				<Plus class="mr-2 h-4 w-4" />
				Create {title.slice(0, -1)}
			</Button>
		{:else if createButton}
			{@render createButton()}
		{/if}
	</div>

	{#if filterSlot}
		<div class="flex items-center gap-2">
			{@render filterSlot()}
		</div>
	{/if}

	<Card>
		<CardHeader>
			<CardTitle>All {title}</CardTitle>
			<CardDescription>{count} total {title.toLowerCase()}</CardDescription>
		</CardHeader>
		<CardContent>
			<Table>
				<TableHeader>
					<TableRow>
						<TableHead class="w-12">
							<Checkbox
								checked={allSelected}
								indeterminate={someSelected}
								onCheckedChange={toggleSelectAll}
								aria-label="Select all"
							/>
						</TableHead>
						{@render tableHead()}
						<TableHead class="w-12"></TableHead>
					</TableRow>
				</TableHeader>
				<TableBody>
					{#if items.length === 0}
						<TableRow>
								<TableCell
									colspan={99}
									class="text-center text-muted-foreground py-8"
								>
								No {title.toLowerCase()} found.
								{#if emptyCreateHref}
									<a href={emptyCreateHref} class="underline">Create your first {title.slice(0, -1).toLowerCase()}</a>.
								{:else if emptyCreateButton}
									{@render emptyCreateButton()}
								{/if}
							</TableCell>
						</TableRow>
					{:else}
						{#each items as item (item[idKey])}
							<TableRow data-state={selectedIds.has(item[idKey]) ? 'selected' : undefined}>
								<TableCell class="w-12">
									<Checkbox
										checked={selectedIds.has(item[idKey])}
										onCheckedChange={() => toggleSelect(item[idKey])}
										aria-label="Select row"
									/>
								</TableCell>
								{@render tableRow(item)}
								<TableCell>
									<DropdownMenu>
										<DropdownMenuTrigger>
											{#snippet child({ props })}
										<Button {...props} variant="ghost" size="icon">
												<MoreHorizontal class="h-4 w-4" />
											</Button>
											{/snippet}
										</DropdownMenuTrigger>
										<DropdownMenuContent align="end">
											<DropdownMenuItem>
												{#snippet child({ props })}
													<a {...props} href={detailHref(item)}>View / Edit</a>
												{/snippet}
											</DropdownMenuItem>
										</DropdownMenuContent>
									</DropdownMenu>
								</TableCell>
							</TableRow>
						{/each}
					{/if}
				</TableBody>
			</Table>

			{#if totalPages > 1}
				<div class="flex items-center justify-end gap-2 mt-4">
					<Button
						variant="outline"
						size="sm"
						disabled={currentPage <= 1}
						href="?offset={Math.max(0, offset - limit)}&limit={limit}{extraParams}"
					>
						Previous
					</Button>
					<span class="text-sm text-muted-foreground">
						Page {currentPage} of {totalPages}
					</span>
					<Button
						variant="outline"
						size="sm"
						disabled={currentPage >= totalPages}
						href="?offset={offset + limit}&limit={limit}{extraParams}"
					>
						Next
					</Button>
				</div>
			{/if}
		</CardContent>
	</Card>
</div>

<!-- Floating bulk action bar -->
{#if selectedCount > 0}
	<div
		class="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 flex items-center gap-3 rounded-lg border bg-card px-4 py-2.5 shadow-lg"
	>
		<span class="text-sm font-medium text-card-foreground">
			{selectedCount} selected
		</span>
		<Button variant="ghost" size="sm" onclick={clearSelection} class="h-7 w-7 p-0">
			<X class="h-4 w-4" />
		</Button>
		<div class="h-4 w-px bg-border"></div>
		<Button
			variant="ghost"
			size="sm"
			class="h-7 gap-1.5 text-destructive hover:text-destructive"
			disabled={archiving}
			onclick={bulkArchive}
		>
			{#if archiving}
				<Loader2 class="h-3.5 w-3.5 animate-spin" />
			{:else}
				<Archive class="h-3.5 w-3.5" />
			{/if}
			Archive
		</Button>
	</div>
{/if}

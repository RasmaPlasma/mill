<script lang="ts">
	import { invalidateAll, goto } from '$app/navigation';
	import { superForm } from 'sveltekit-superforms';
	import { Button } from '$lib/components/ui/button';
	import { Badge } from '$lib/components/ui/badge';
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
	import {
		Sheet,
		SheetContent,
		SheetHeader,
		SheetTitle,
		SheetDescription,
	} from '$lib/components/ui/sheet';
	import {
		AlertDialog,
		AlertDialogAction,
		AlertDialogCancel,
		AlertDialogContent,
		AlertDialogDescription,
		AlertDialogFooter,
		AlertDialogHeader,
		AlertDialogTitle,
	} from '$lib/components/ui/alert-dialog';
	import * as Select from '$lib/components/ui/select';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import { Separator } from '$lib/components/ui/separator';
	import { toast } from 'svelte-sonner';
	import { MoreHorizontal, Plus, Loader2, Trash2 } from 'lucide-svelte';

	let { data } = $props();
	let sheetOpen = $state(false);
	let editingSecret = $state<any>(null);
	let deleteTarget = $state<any>(null);

	let totalPages = $derived(Math.ceil(data.count / data.limit));
	let currentPage = $derived(Math.floor(data.offset / data.limit) + 1);

	const { form, errors, enhance, submitting, delayed } = superForm(data.form, {
		applyAction: false,
		invalidateAll: false,
		onResult: ({ result }) => {
			if (result.type === 'success') {
				sheetOpen = false;
				editingSecret = null;
				toast.success(editingSecret ? 'Secret updated' : 'Secret created');
				invalidateAll();
			}
			if (result.type === 'failure') {
				const err = result.data?.error;
				if (err) toast.error(err);
			}
		},
	});

	function openCreate() {
		editingSecret = null;
		$form.name = '';
		$form.value = '';
		$form.scope = 'global';
		$form.description = '';
		sheetOpen = true;
	}

	function openEdit(secret: any) {
		editingSecret = secret;
		$form.name = secret.name;
		$form.value = '';
		$form.scope = secret.scope;
		$form.description = secret.description || '';
		sheetOpen = true;
	}

	async function doDelete() {
		if (!deleteTarget) return;
		const fd = new FormData();
		fd.append('id', deleteTarget.id);
		try {
			const res = await fetch('?/delete', { method: 'POST', body: fd });
			if (!res.ok) {
				const err = await res.json();
				throw new Error(err.error || 'Delete failed');
			}
			toast.success('Secret deleted');
			invalidateAll();
		} catch (err: any) {
			toast.error(err.message);
		} finally {
			deleteTarget = null;
		}
	}

	function scopeLabel(scope: string): string {
		if (scope === 'global') return 'Global';
		if (scope.startsWith('agent:')) {
			const id = scope.slice(6);
			const agent = data.agents.find((a: any) => a.id === id);
			return agent ? `Agent: ${agent.name}` : scope;
		}
		if (scope.startsWith('environment:')) {
			const id = scope.slice(14);
			const env = data.environments.find((e: any) => e.id === id);
			return env ? `Env: ${env.name}` : scope;
		}
		return scope;
	}

	function scopeOptions(): Array<{ value: string; label: string }> {
		const opts = [{ value: 'global', label: 'Global' }];
		for (const a of data.agents) {
			opts.push({ value: `agent:${a.id}`, label: `Agent: ${a.name}` });
		}
		for (const e of data.environments) {
			opts.push({ value: `environment:${e.id}`, label: `Env: ${e.name}` });
		}
		return opts;
	}

	function formatDate(d: string | null) {
		if (!d) return '-';
		return new Date(d).toLocaleDateString();
	}
</script>

<div class="space-y-4">
	<div class="flex items-center justify-between">
		<div>
			<h2 class="text-2xl font-bold tracking-tight">Secrets</h2>
			<p class="text-muted-foreground">Manage encrypted secrets.</p>
		</div>
		<Button onclick={openCreate}>
			<Plus class="mr-2 h-4 w-4" />
			Add Secret
		</Button>
	</div>

	<div class="flex items-center gap-2">
		<Select.Root
			type="single"
			value={data.scope}
			onValueChange={(val) => goto(`?scope=${val}&offset=0&limit=${data.limit}`)}
		>
			<Select.Trigger class="w-[220px]">
				<Select.Value placeholder="Filter by scope" />
			</Select.Trigger>
			<Select.Content>
				<Select.Item value="" label="All scopes">All scopes</Select.Item>
				{#each scopeOptions() as opt}
					<Select.Item value={opt.value} label={opt.label}>{opt.label}</Select.Item>
				{/each}
			</Select.Content>
		</Select.Root>
	</div>

	<Card>
		<CardHeader>
			<CardTitle>All Secrets</CardTitle>
			<CardDescription>{data.count} total secrets</CardDescription>
		</CardHeader>
		<CardContent>
			<Table>
				<TableHeader>
					<TableRow>
						<TableHead>Name</TableHead>
						<TableHead>Scope</TableHead>
						<TableHead>Description</TableHead>
						<TableHead>Created</TableHead>
						<TableHead class="w-12"></TableHead>
					</TableRow>
				</TableHeader>
				<TableBody>
					{#if data.secrets.length === 0}
						<TableRow>
							<TableCell colspan={5} class="text-center text-muted-foreground py-8">
								No secrets found. <button class="underline" onclick={openCreate}>Add your first secret</button>.
							</TableCell>
						</TableRow>
					{:else}
						{#each data.secrets as secret (secret.id)}
							<TableRow>
								<TableCell class="font-medium">{secret.name}</TableCell>
								<TableCell>
									<Badge variant="outline">{scopeLabel(secret.scope)}</Badge>
								</TableCell>
								<TableCell class="text-muted-foreground">
									{secret.description || '-'}
								</TableCell>
								<TableCell class="text-muted-foreground">
									{formatDate(secret.created_at)}
								</TableCell>
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
											<DropdownMenuItem onclick={() => openEdit(secret)}>
												Edit
											</DropdownMenuItem>
											<DropdownMenuItem
												class="text-destructive focus:text-destructive"
												onclick={() => (deleteTarget = secret)}
											>
												<Trash2 class="h-4 w-4 mr-1" />
												Delete
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
						href="?offset={Math.max(0, data.offset - data.limit)}&limit={data.limit}{data.scope ? `&scope=${data.scope}` : ''}"
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
						href="?offset={data.offset + data.limit}&limit={data.limit}{data.scope ? `&scope=${data.scope}` : ''}"
					>
						Next
					</Button>
				</div>
			{/if}
		</CardContent>
	</Card>
</div>

<Sheet bind:open={sheetOpen}>
	<SheetContent class="sm:max-w-md">
		<SheetHeader>
			<SheetTitle>{editingSecret ? 'Edit Secret' : 'Add Secret'}</SheetTitle>
			<SheetDescription>
				{editingSecret ? 'Update the secret value (name cannot be changed).' : 'Create a new encrypted secret.'}
			</SheetDescription>
		</SheetHeader>
		<form method="POST" action="?/upsert" use:enhance class="space-y-4 py-4">
			<div class="space-y-2">
				<Label for="name">Name</Label>
				<Input id="name" name="name" bind:value={$form.name} disabled={!!editingSecret} />
				{#if $errors.name}<p class="text-sm text-destructive">{$errors.name}</p>{/if}
			</div>
			<div class="space-y-2">
				<Label for="value">Value</Label>
				<Input id="value" name="value" bind:value={$form.value} type="password" />
				{#if $errors.value}<p class="text-sm text-destructive">{$errors.value}</p>{/if}
				{#if editingSecret}
					<p class="text-xs text-muted-foreground">Re-enter the value (previous value is never returned).</p>
				{/if}
			</div>
			<div class="space-y-2">
				<Label for="scope">Scope</Label>
				<Select.Root type="single" bind:value={$form.scope} name="scope">
					<Select.Trigger id="scope">
						<Select.Value placeholder="Select scope" />
					</Select.Trigger>
					<Select.Content>
						{#each scopeOptions() as opt}
							<Select.Item value={opt.value} label={opt.label}>{opt.label}</Select.Item>
						{/each}
					</Select.Content>
				</Select.Root>
			</div>
			<div class="space-y-2">
				<Label for="description">Description</Label>
				<Input id="description" name="description" bind:value={$form.description} />
			</div>
			<Separator />
			<div class="flex items-center gap-2 pt-2">
				<Button type="submit" disabled={$submitting || $delayed}>
					{#if $submitting || $delayed}
						<Loader2 class="mr-2 h-4 w-4 animate-spin" />
						Saving...
					{:else}
						{editingSecret ? 'Update Secret' : 'Add Secret'}
					{/if}
				</Button>
				<Button type="button" variant="ghost" onclick={() => { sheetOpen = false; editingSecret = null; }}>
					Cancel
				</Button>
			</div>
		</form>
	</SheetContent>
</Sheet>

<AlertDialog open={!!deleteTarget} onOpenChange={(open) => { if (!open) deleteTarget = null; }}>
	<AlertDialogContent>
		<AlertDialogHeader>
			<AlertDialogTitle>Delete Secret</AlertDialogTitle>
			<AlertDialogDescription>
				Are you sure you want to delete the secret "{deleteTarget?.name}"? This action cannot be undone.
			</AlertDialogDescription>
		</AlertDialogHeader>
		<AlertDialogFooter>
			<AlertDialogCancel onclick={() => (deleteTarget = null)}>Cancel</AlertDialogCancel>
			<AlertDialogAction onclick={doDelete} class="bg-destructive text-destructive-foreground hover:bg-destructive/90">
				Delete
			</AlertDialogAction>
		</AlertDialogFooter>
	</AlertDialogContent>
</AlertDialog>

<script lang="ts">
	import { invalidateAll } from '$app/navigation';
	import { enhance as sveltekitEnhance } from '$app/forms';
	import { superForm } from 'sveltekit-superforms';
	import { Button } from '$lib/components/ui/button';
	import { Badge } from '$lib/components/ui/badge';
	import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import { Tabs, TabsContent, TabsList, TabsTrigger } from '$lib/components/ui/tabs';
	import {
		AlertDialog,
		AlertDialogAction,
		AlertDialogCancel,
		AlertDialogContent,
		AlertDialogDescription,
		AlertDialogFooter,
		AlertDialogHeader,
		AlertDialogTitle,
		AlertDialogTrigger,
	} from '$lib/components/ui/alert-dialog';
	import {
		Dialog,
		DialogContent,
		DialogHeader,
		DialogTitle,
		DialogDescription,
		DialogFooter,
	} from '$lib/components/ui/dialog';
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
	import { Separator } from '$lib/components/ui/separator';
	import * as Select from '$lib/components/ui/select';
	import { toast } from 'svelte-sonner';
	import { ArrowLeft, Loader2, Archive, Plus, MoreHorizontal } from 'lucide-svelte';

	let { data } = $props();

	let addCredOpen = $state(false);
	let rotateCredOpen = $state(false);
	let rotateTarget = $state<any>(null);

	const { form, errors, enhance, submitting, delayed } = superForm(data.form, {
		applyAction: false,
		invalidateAll: false,
		onResult: ({ result }) => {
			if (result.type === 'failure') {
				const err = result.data?.error;
				if (err) toast.error(err);
			}
			if (result.type === 'redirect') {
				toast.success('Vault updated');
				invalidateAll();
			}
		},
	});



	function openRotate(cred: any) {
		rotateTarget = cred;
		rotateCredOpen = true;
	}

	function formatDate(d: string | null) {
		if (!d) return '-';
		return new Date(d).toLocaleDateString();
	}
</script>

<div class="space-y-4 max-w-4xl">
	<div class="flex items-center justify-between">
		<div class="flex items-center gap-2">
			<Button variant="ghost" size="icon" href="/vaults">
				<ArrowLeft class="h-4 w-4" />
			</Button>
			<div>
				<h2 class="text-2xl font-bold tracking-tight">{data.vault.display_name}</h2>
				<p class="text-muted-foreground">Vault details and credentials.</p>
			</div>
		</div>
		<AlertDialog>
			<AlertDialogTrigger>
				{#snippet child({ props })}
					<Button {...props} variant="destructive" size="sm">
						<Archive class="mr-2 h-4 w-4" />
						Archive
					</Button>
				{/snippet}
			</AlertDialogTrigger>
			<AlertDialogContent>
				<AlertDialogHeader>
					<AlertDialogTitle>Archive Vault</AlertDialogTitle>
					<AlertDialogDescription>
						This will archive the vault "{data.vault.display_name}" and all its credentials.
					</AlertDialogDescription>
				</AlertDialogHeader>
				<AlertDialogFooter>
					<AlertDialogCancel>Cancel</AlertDialogCancel>
					<form method="POST" action="?/archive" class="inline">
						<AlertDialogAction type="submit" class="bg-destructive text-destructive-foreground hover:bg-destructive/90">
							Archive
						</AlertDialogAction>
					</form>
				</AlertDialogFooter>
			</AlertDialogContent>
		</AlertDialog>
	</div>

	<Tabs value="overview" class="w-full">
		<TabsList>
			<TabsTrigger value="overview">Overview</TabsTrigger>
			<TabsTrigger value="credentials">Credentials</TabsTrigger>
		</TabsList>

		<TabsContent value="overview" class="space-y-4">
			<Card>
				<CardHeader>
					<CardTitle>Details</CardTitle>
				</CardHeader>
				<CardContent class="space-y-4">
					<div class="grid grid-cols-[120px_1fr] gap-2 text-sm">
						<span class="text-muted-foreground">ID</span>
						<span class="font-mono text-xs">{data.vault.id}</span>

						<span class="text-muted-foreground">Display Name</span>
						<span class="font-medium">{data.vault.display_name}</span>

						<span class="text-muted-foreground">Metadata</span>
						<span class="text-muted-foreground">
							{Object.keys(data.vault.metadata || {}).length ? JSON.stringify(data.vault.metadata) : '-'}
						</span>

						<span class="text-muted-foreground">Created</span>
						<span>{formatDate(data.vault.created_at)}</span>

						<span class="text-muted-foreground">Updated</span>
						<span>{formatDate(data.vault.updated_at)}</span>
					</div>
					<Separator />
					<form method="POST" action="?/update" use:enhance class="space-y-4">
						<div class="space-y-2">
							<Label for="display_name">Display Name</Label>
							<Input id="display_name" name="display_name" bind:value={$form.display_name} />
							{#if $errors.display_name}<p class="text-sm text-destructive">{$errors.display_name}</p>{/if}
						</div>
						<div class="space-y-2">
							<Label for="metadata_json">Metadata (JSON)</Label>
							<Input id="metadata_json" name="metadata_json" bind:value={$form.metadata_json as string} />
						</div>
						<div class="flex items-center gap-2 pt-2">
							<Button type="submit" disabled={$submitting || $delayed}>
								{#if $submitting || $delayed}
									<Loader2 class="mr-2 h-4 w-4 animate-spin" />
									Saving...
								{:else}
									Save Changes
								{/if}
							</Button>
							<Button type="button" variant="outline" href="/vaults">Cancel</Button>
						</div>
					</form>
				</CardContent>
			</Card>
		</TabsContent>

		<TabsContent value="credentials" class="space-y-4">
			<Card>
				<CardHeader class="flex flex-row items-center justify-between">
					<div>
						<CardTitle>Credentials</CardTitle>
						<CardDescription>MCP server credentials in this vault.</CardDescription>
					</div>
					<Button size="sm" onclick={() => (addCredOpen = true)}>
						<Plus class="mr-2 h-4 w-4" />
						Add Credential
					</Button>
				</CardHeader>
				<CardContent>
					{#if !data.vault.credentials?.length}
						<p class="text-sm text-muted-foreground text-center py-8">
							No credentials. <button class="underline" onclick={() => (addCredOpen = true)}>Add your first credential</button>.
						</p>
					{:else}
						<Table>
							<TableHeader>
								<TableRow>
									<TableHead>Display Name</TableHead>
									<TableHead>MCP Server URL</TableHead>
									<TableHead>Auth Type</TableHead>
									<TableHead>Expires</TableHead>
									<TableHead class="w-12"></TableHead>
								</TableRow>
							</TableHeader>
							<TableBody>
								{#each data.vault.credentials as cred (cred.id)}
									<TableRow>
										<TableCell class="font-medium">{cred.display_name}</TableCell>
										<TableCell class="text-muted-foreground text-xs max-w-[200px] truncate">
											{cred.mcp_server_url}
										</TableCell>
										<TableCell>
											<Badge variant="outline">{cred.auth_type}</Badge>
										</TableCell>
										<TableCell class="text-muted-foreground">
											{formatDate(cred.expires_at)}
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
													<DropdownMenuItem onclick={() => openRotate(cred)}>
														Rotate
													</DropdownMenuItem>
												</DropdownMenuContent>
											</DropdownMenu>
										</TableCell>
									</TableRow>
								{/each}
							</TableBody>
						</Table>
					{/if}
				</CardContent>
			</Card>
		</TabsContent>
	</Tabs>
</div>

<!-- Add Credential Dialog -->
<Dialog bind:open={addCredOpen}>
	<DialogContent class="sm:max-w-lg">
		<DialogHeader>
			<DialogTitle>Add Credential</DialogTitle>
			<DialogDescription>Add a new MCP server credential.</DialogDescription>
		</DialogHeader>
		<form
			method="POST"
			action="?/createCredential"
			use:sveltekitEnhance={() => {
				return async ({ result }) => {
					if (result.type === 'success') {
						addCredOpen = false;
						toast.success('Credential saved');
						invalidateAll();
					}
					if (result.type === 'failure') {
						const err = (result.data as any)?.error;
						if (err) toast.error(err);
					}
				};
			}}
			class="space-y-4 py-2"
		>
			<div class="space-y-2">
				<Label for="display_name">Display Name</Label>
				<Input id="display_name" name="display_name" />
			</div>
			<div class="space-y-2">
				<Label for="mcp_server_url">MCP Server URL</Label>
				<Input id="mcp_server_url" name="mcp_server_url" type="url" placeholder="https://..." />
			</div>
			<div class="space-y-2">
				<Label for="auth_type">Auth Type</Label>
				<Select.Root type="single" name="auth_type">
					<Select.Trigger id="auth_type">
						<Select.Value placeholder="Select type" />
					</Select.Trigger>
					<Select.Content>
						<Select.Item value="mcp_oauth" label="MCP OAuth">MCP OAuth</Select.Item>
						<Select.Item value="static_bearer" label="Static Bearer">Static Bearer</Select.Item>
					</Select.Content>
				</Select.Root>
			</div>
			<div class="space-y-2">
				<Label for="token">Token</Label>
				<Input id="token" name="token" type="password" />
			</div>
			<div class="space-y-2">
				<Label for="refresh_token">Refresh Token</Label>
				<Input id="refresh_token" name="refresh_token" type="password" />
			</div>
			<div class="space-y-2">
				<Label for="token_endpoint">Token Endpoint</Label>
				<Input id="token_endpoint" name="token_endpoint" type="url" />
			</div>
			<div class="grid grid-cols-2 gap-4">
				<div class="space-y-2">
					<Label for="client_id">Client ID</Label>
					<Input id="client_id" name="client_id" />
				</div>
				<div class="space-y-2">
					<Label for="scope">Scope</Label>
					<Input id="scope" name="scope" />
				</div>
			</div>
			<div class="space-y-2">
				<Label for="expires_at">Expires At</Label>
				<Input id="expires_at" name="expires_at" type="datetime-local" />
			</div>
			<DialogFooter>
				<Button type="button" variant="ghost" onclick={() => (addCredOpen = false)}>Cancel</Button>
				<Button type="submit">Add Credential</Button>
			</DialogFooter>
		</form>
	</DialogContent>
</Dialog>

<!-- Rotate Credential Dialog -->
<Dialog bind:open={rotateCredOpen}>
	<DialogContent class="sm:max-w-md">
		<DialogHeader>
			<DialogTitle>Rotate Credential</DialogTitle>
			<DialogDescription>Update token for {rotateTarget?.display_name || ''}.</DialogDescription>
		</DialogHeader>
		<form
			method="POST"
			action="?/rotateCredential"
			use:sveltekitEnhance={() => {
				return async ({ result }) => {
					if (result.type === 'success') {
						rotateCredOpen = false;
						rotateTarget = null;
						toast.success('Credential rotated');
						invalidateAll();
					}
					if (result.type === 'failure') {
						const err = (result.data as any)?.error;
						if (err) toast.error(err);
					}
				};
			}}
			class="space-y-4 py-2"
		>
			<input type="hidden" name="credential_id" value={rotateTarget?.id || ''} />
			<div class="space-y-2">
				<Label for="rotate_token">New Token</Label>
				<Input id="rotate_token" name="token" type="password" />
			</div>
			<div class="space-y-2">
				<Label for="rotate_refresh_token">New Refresh Token</Label>
				<Input id="rotate_refresh_token" name="refresh_token" type="password" />
			</div>
			<div class="space-y-2">
				<Label for="rotate_expires_at">New Expires At</Label>
				<Input id="rotate_expires_at" name="expires_at" type="datetime-local" />
			</div>
			<DialogFooter>
				<Button type="button" variant="ghost" onclick={() => { rotateCredOpen = false; rotateTarget = null; }}>Cancel</Button>
				<Button type="submit">Rotate Credential</Button>
			</DialogFooter>
		</form>
	</DialogContent>
</Dialog>

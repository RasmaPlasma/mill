<script lang="ts">
	import { superForm } from 'sveltekit-superforms';
	import { Button } from '$lib/components/ui/button';
	import { Badge } from '$lib/components/ui/badge';
	import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import { Textarea } from '$lib/components/ui/textarea';
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
	import { Separator } from '$lib/components/ui/separator';
	import { toast } from 'svelte-sonner';
	import { ArrowLeft, Loader2, Archive } from 'lucide-svelte';

	let { data } = $props();

	const { form, errors, enhance, submitting, delayed } = superForm(data.form, {
		onResult: ({ result }) => {
			if (result.type === 'failure') {
				const err = result.data?.error;
				if (err) toast.error(err);
			}
		},
	});
</script>

<div class="space-y-4 max-w-3xl">
	<div class="flex items-center justify-between">
		<div class="flex items-center gap-2">
			<Button variant="ghost" size="icon" href="/models">
				<ArrowLeft class="h-4 w-4" />
			</Button>
			<div>
				<h2 class="text-2xl font-bold tracking-tight">{data.model.display_name}</h2>
				<p class="text-muted-foreground flex items-center gap-2">
					<Badge variant="secondary">{data.model.provider}</Badge>
				</p>
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
					<AlertDialogTitle>Archive Model</AlertDialogTitle>
					<AlertDialogDescription>
						This will archive the model "{data.model.display_name}". It will no longer be available for new agents.
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
			<TabsTrigger value="edit">Edit</TabsTrigger>
		</TabsList>

		<TabsContent value="overview" class="space-y-4">
			<Card>
				<CardHeader>
					<CardTitle>Details</CardTitle>
				</CardHeader>
				<CardContent class="space-y-4">
					<div class="grid grid-cols-[120px_1fr] gap-2 text-sm">
						<span class="text-muted-foreground">Display Name</span>
						<span class="font-medium">{data.model.display_name}</span>

						<span class="text-muted-foreground">Provider</span>
						<Badge variant="secondary" class="w-fit">{data.model.provider}</Badge>

						<span class="text-muted-foreground">Provider Model ID</span>
						<span class="font-mono text-xs bg-muted px-2 py-1 rounded w-fit">{data.model.provider_model}</span>

						<span class="text-muted-foreground">Description</span>
						<span class="text-muted-foreground">{data.model.description || '-'}</span>

						<span class="text-muted-foreground">Created</span>
						<span class="text-muted-foreground">{new Date(data.model.created_at).toLocaleString()}</span>
					</div>
				</CardContent>
			</Card>
		</TabsContent>

		<TabsContent value="edit">
			<Card>
				<CardHeader>
					<CardTitle>Edit Model</CardTitle>
					<CardDescription>Update model configuration.</CardDescription>
				</CardHeader>
				<CardContent>
					<form method="POST" action="?/update" use:enhance class="space-y-6">
						<div class="space-y-2">
							<Label for="display_name">Display Name</Label>
							<Input id="display_name" name="display_name" bind:value={$form.display_name} />
							{#if $errors.display_name}<p class="text-sm text-destructive">{$errors.display_name}</p>{/if}
						</div>

						<div class="space-y-2">
							<Label for="provider">Provider</Label>
							<Input id="provider" name="provider" bind:value={$form.provider} />
							{#if $errors.provider}<p class="text-sm text-destructive">{$errors.provider}</p>{/if}
						</div>

						<div class="space-y-2">
							<Label for="provider_model">Provider Model ID</Label>
							<Input id="provider_model" name="provider_model" bind:value={$form.provider_model} />
							{#if $errors.provider_model}<p class="text-sm text-destructive">{$errors.provider_model}</p>{/if}
						</div>

						<div class="space-y-2">
							<Label for="description">Description</Label>
							<Textarea id="description" name="description" bind:value={$form.description} />
						</div>

						<div class="flex items-center gap-4 pt-4">
							<Button type="submit" disabled={$submitting || $delayed}>
								{#if $submitting || $delayed}
									<Loader2 class="mr-2 h-4 w-4 animate-spin" />
									Saving...
								{:else}
									Save Changes
								{/if}
							</Button>
							<Button type="button" variant="outline" href="/models">Cancel</Button>
						</div>
					</form>
				</CardContent>
			</Card>
		</TabsContent>
	</Tabs>
</div>

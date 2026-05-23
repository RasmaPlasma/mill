<script lang="ts">
	import { superForm } from 'sveltekit-superforms';
	import { Button } from '$lib/components/ui/button';
	import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import { Textarea } from '$lib/components/ui/textarea';
	import { toast } from 'svelte-sonner';
	import { ArrowLeft, Loader2 } from 'lucide-svelte';

	let { data } = $props();

	const { form, errors, enhance, submitting, delayed } = superForm(data.form, {
		onResult: ({ result }) => {
			if (result.type === 'failure') {
				const err = result.data?.error;
				if (err) toast.error(err);
			}
			if (result.type === 'redirect') {
				toast.success('Model added successfully');
			}
		},
	});
</script>

<div class="space-y-4 max-w-3xl">
	<div class="flex items-center gap-2">
		<Button variant="ghost" size="icon" href="/models">
			<ArrowLeft class="h-4 w-4" />
		</Button>
		<div>
			<h2 class="text-2xl font-bold tracking-tight">Add Model</h2>
			<p class="text-muted-foreground">Configure a new LLM model.</p>
		</div>
	</div>

	<Card>
		<CardHeader>
			<CardTitle>Model Configuration</CardTitle>
			<CardDescription>Define the display name, provider, and provider model ID.</CardDescription>
		</CardHeader>
		<CardContent>
			<form method="POST" use:enhance class="space-y-6">
				<div class="space-y-2">
					<Label for="display_name">Display Name</Label>
					<Input id="display_name" name="display_name" bind:value={$form.display_name} placeholder="Kimi K2.6 Turbo" />
					{#if $errors.display_name}<p class="text-sm text-destructive">{$errors.display_name}</p>{/if}
				</div>

				<div class="space-y-2">
					<Label for="provider">Provider</Label>
					<Input id="provider" name="provider" bind:value={$form.provider} placeholder="fireworks" />
					<p class="text-xs text-muted-foreground">e.g. fireworks, nvidia, openai</p>
					{#if $errors.provider}<p class="text-sm text-destructive">{$errors.provider}</p>{/if}
				</div>

				<div class="space-y-2">
					<Label for="provider_model">Provider Model ID</Label>
					<Input id="provider_model" name="provider_model" bind:value={$form.provider_model} placeholder="accounts/fireworks/routers/kimi-k2p6-turbo" />
					<p class="text-xs text-muted-foreground">The raw model identifier from the provider.</p>
					{#if $errors.provider_model}<p class="text-sm text-destructive">{$errors.provider_model}</p>{/if}
				</div>

				<div class="space-y-2">
					<Label for="description">Description</Label>
					<Textarea id="description" name="description" bind:value={$form.description} placeholder="Optional description..." />
				</div>

				<div class="flex items-center gap-4 pt-4">
					<Button type="submit" disabled={$submitting || $delayed}>
						{#if $submitting || $delayed}
							<Loader2 class="mr-2 h-4 w-4 animate-spin" />
							Adding...
						{:else}
							Add Model
						{/if}
					</Button>
					<Button type="button" variant="outline" href="/models">Cancel</Button>
				</div>
			</form>
		</CardContent>
	</Card>
</div>

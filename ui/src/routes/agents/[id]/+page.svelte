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
		Accordion,
		AccordionContent,
		AccordionItem,
		AccordionTrigger,
	} from '$lib/components/ui/accordion';
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
	import * as Select from '$lib/components/ui/select';
	import { ScrollArea } from '$lib/components/ui/scroll-area';
	import { Separator } from '$lib/components/ui/separator';
	import { toast } from 'svelte-sonner';
	import { ArrowLeft, Loader2, Archive } from 'lucide-svelte';
	import TagsInput from '$lib/components/tags-input.svelte';
	import CodeEditor from '$lib/components/code-editor.svelte';

	let { data } = $props();

	const { form, errors, enhance, submitting, delayed } = superForm(data.form, {
		onResult: ({ result }) => {
			if (result.type === 'failure') {
				const err = result.data?.error;
				if (err) toast.error(err);
			}
		},
	});

	let tools = $derived(data.agent.tools || []);

	function formatDate(d: string | null) {
		if (!d) return '-';
		return new Date(d).toLocaleString();
	}
</script>

<div class="space-y-4 max-w-3xl">
	<div class="flex items-center justify-between">
		<div class="flex items-center gap-2">
			<Button variant="ghost" size="icon" href="/agents">
				<ArrowLeft class="h-4 w-4" />
			</Button>
			<div>
				<h2 class="text-2xl font-bold tracking-tight">{data.agent.name}</h2>
				<p class="text-muted-foreground flex items-center gap-2">
					<Badge variant="outline" class="max-w-[300px]">
						<span class="truncate" title={data.agent.model}>{data.agent.model}</span>
					</Badge>
					<Badge variant="secondary">v{data.agent.version}</Badge>
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
					<AlertDialogTitle>Archive Agent</AlertDialogTitle>
					<AlertDialogDescription>
						This will archive the agent "{data.agent.name}". It will no longer appear in lists or be usable in new sessions.
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
						<span class="text-muted-foreground">Name</span>
						<span class="font-medium">{data.agent.name}</span>

						<span class="text-muted-foreground">Model</span>
						<Badge variant="outline" class="w-fit max-w-[300px]">
							<span class="truncate" title={data.agent.model}>{data.agent.model}</span>
						</Badge>

						<span class="text-muted-foreground">Version</span>
						<span>v{data.agent.version}</span>

						<span class="text-muted-foreground">Description</span>
						<span class="text-muted-foreground">{data.agent.description || '-'}</span>

						<span class="text-muted-foreground">Created</span>
						<span class="text-muted-foreground">{formatDate(data.agent.created_at)}</span>

						<span class="text-muted-foreground">Updated</span>
						<span class="text-muted-foreground">{formatDate(data.agent.updated_at)}</span>
					</div>
					<Separator />
					<div class="space-y-2">
						<span class="text-sm font-medium">System Prompt</span>
						<ScrollArea class="h-[200px] rounded-md border p-3 bg-muted/30">
							<pre class="text-sm whitespace-pre-wrap">{data.agent.system_prompt || '-'}</pre>
						</ScrollArea>
					</div>
					{#if data.agent.tools?.length > 0}
						<div class="space-y-2">
							<span class="text-sm font-medium">Tools</span>
							<div class="flex flex-wrap gap-2">
								{#each data.agent.tools as tool}
									<Badge variant="secondary">{tool}</Badge>
								{/each}
							</div>
						</div>
					{/if}
					{#if data.agent.mcp_servers?.length > 0}
						<div class="space-y-2">
							<span class="text-sm font-medium">MCP Servers</span>
							<ScrollArea class="h-[160px] rounded-md border p-3 bg-muted/30">
								<pre class="text-xs">{JSON.stringify(data.agent.mcp_servers, null, 2)}</pre>
							</ScrollArea>
						</div>
					{/if}
				</CardContent>
			</Card>
		</TabsContent>

		<TabsContent value="edit">
			<Card>
				<CardHeader>
					<CardTitle>Edit Agent</CardTitle>
					<CardDescription>Update agent configuration. A new version will be created.</CardDescription>
				</CardHeader>
				<CardContent>
					<form method="POST" action="?/update" use:enhance class="space-y-6">
						<div class="space-y-2">
							<Label for="name">Name</Label>
							<Input id="name" name="name" bind:value={$form.name} />
							{#if $errors.name}<p class="text-sm text-destructive">{$errors.name}</p>{/if}
						</div>

						<div class="space-y-2">
							<Label for="model_id">Model</Label>
						<Select.Root type="single" bind:value={$form.model_id} name="model_id">
							<Select.Trigger class="w-full" id="model_id">
								<Select.Value placeholder="Select a model" />
							</Select.Trigger>
							<Select.Content>
								{#each data.models as model}
									<Select.Item value={model.id} label="{model.display_name} ({model.provider})">
										{model.display_name}
										<span class="text-muted-foreground text-xs ml-1">({model.provider})</span>
									</Select.Item>
								{/each}
							</Select.Content>
						</Select.Root>
							{#if $errors.model_id}<p class="text-sm text-destructive">{$errors.model_id}</p>{/if}
						</div>

						<div class="space-y-2">
							<Label for="description">Description</Label>
							<Textarea id="description" name="description" bind:value={$form.description} />
						</div>

						<div class="space-y-2">
							<Label for="system_prompt">System Prompt</Label>
							<CodeEditor bind:value={$form.system_prompt} />
							<input type="hidden" name="system_prompt" value={$form.system_prompt} />
						</div>

						<div class="space-y-2">
							<Label>Tools</Label>
							<TagsInput bind:value={tools} />
							<input type="hidden" name="tools" value={tools.join('\n')} />
						</div>

						<Accordion type="single">
							<AccordionItem value="advanced">
								<AccordionTrigger>Advanced Options</AccordionTrigger>
								<AccordionContent class="space-y-4 pt-2">
									<div class="space-y-2">
										<Label for="mcp_servers_json">MCP Servers (JSON)</Label>
										<Textarea
											id="mcp_servers_json"
											name="mcp_servers_json"
											bind:value={$form.mcp_servers_json as string}
											rows={6}
										/>
									</div>
									<div class="space-y-2">
										<Label for="metadata_json">Metadata (JSON)</Label>
										<Textarea
											id="metadata_json"
											name="metadata_json"
											bind:value={$form.metadata_json as string}
											rows={4}
										/>
									</div>
								</AccordionContent>
								</AccordionItem>
							</Accordion>

						<div class="flex items-center gap-4 pt-4">
							<Button type="submit" disabled={$submitting || $delayed}>
								{#if $submitting || $delayed}
									<Loader2 class="mr-2 h-4 w-4 animate-spin" />
									Saving...
								{:else}
									Save Changes
								{/if}
							</Button>
							<Button type="button" variant="outline" href="/agents">Cancel</Button>
						</div>
					</form>
				</CardContent>
			</Card>
		</TabsContent>
	</Tabs>
</div>

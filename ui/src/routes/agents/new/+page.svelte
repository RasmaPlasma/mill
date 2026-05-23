<script lang="ts">
	import { superForm } from 'sveltekit-superforms';
	import { Button } from '$lib/components/ui/button';
	import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import { Textarea } from '$lib/components/ui/textarea';
	import {
		Accordion,
		AccordionContent,
		AccordionItem,
		AccordionTrigger,
	} from '$lib/components/ui/accordion';
	import * as Select from '$lib/components/ui/select';
	import { toast } from 'svelte-sonner';
	import { ArrowLeft, Loader2 } from 'lucide-svelte';
	import TagsInput from '$lib/components/tags-input.svelte';
	import CodeEditor from '$lib/components/code-editor.svelte';

	let { data } = $props();

	const { form, errors, enhance, submitting, delayed } = superForm(data.form, {
		onResult: ({ result }) => {
			if (result.type === 'failure') {
				const err = result.data?.error;
				if (err) toast.error(err);
			}
			if (result.type === 'redirect') {
				toast.success('Agent created successfully');
			}
		},
	});

	let tools = $state<string[]>([]);
</script>

<div class="space-y-4 max-w-3xl">
	<div class="flex items-center gap-2">
		<Button variant="ghost" size="icon" href="/agents">
			<ArrowLeft class="h-4 w-4" />
		</Button>
		<div>
			<h2 class="text-2xl font-bold tracking-tight">Create Agent</h2>
			<p class="text-muted-foreground">Configure a new agent.</p>
		</div>
	</div>

	<Card>
		<CardHeader>
			<CardTitle>Agent Configuration</CardTitle>
			<CardDescription>Define the agent's model, prompt, and capabilities.</CardDescription>
		</CardHeader>
		<CardContent>
			<form method="POST" use:enhance class="space-y-6">
				<div class="space-y-2">
					<Label for="name">Name</Label>
					<Input id="name" name="name" bind:value={$form.name} placeholder="My Agent" />
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
					<Textarea id="description" name="description" bind:value={$form.description} placeholder="What does this agent do?" />
				</div>

				<div class="space-y-2">
					<Label for="system_prompt">System Prompt</Label>
					<CodeEditor bind:value={$form.system_prompt} placeholder="You are a helpful assistant..." />
					<input type="hidden" name="system_prompt" value={$form.system_prompt} />
				</div>

				<div class="space-y-2">
					<Label>Tools</Label>
					<TagsInput bind:value={tools} placeholder="Add tool and press Enter..." />
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
									placeholder={`[\n  {\n    "name": "my-server",\n    "transport": "stdio",\n    "command": "python",\n    "args": ["/path/to/server.py"]\n  }\n]`}
									rows={6}
								/>
								{#if $errors.mcp_servers_json}<p class="text-sm text-destructive">{$errors.mcp_servers_json}</p>{/if}
							</div>
							<div class="space-y-2">
								<Label for="metadata_json">Metadata (JSON)</Label>
								<Textarea
									id="metadata_json"
									name="metadata_json"
									bind:value={$form.metadata_json as string}
									placeholder={`{\n  "key": "value"\n}`}
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
							Creating...
						{:else}
							Create Agent
						{/if}
					</Button>
					<Button type="button" variant="outline" href="/agents">Cancel</Button>
				</div>
			</form>
		</CardContent>
	</Card>
</div>

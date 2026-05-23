<script lang="ts">
	import { invalidateAll, goto } from '$app/navigation';
	import { superForm } from 'sveltekit-superforms';
	import ResourceList from '$lib/components/resource-list.svelte';
	import { Button } from '$lib/components/ui/button';
	import { TableCell, TableHead } from '$lib/components/ui/table';
	import {
		Sheet,
		SheetContent,
		SheetHeader,
		SheetTitle,
		SheetDescription,
	} from '$lib/components/ui/sheet';
	import * as Select from '$lib/components/ui/select';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import { Separator } from '$lib/components/ui/separator';
	import { toast } from 'svelte-sonner';
	import { Plus, Loader2 } from 'lucide-svelte';
	import StatusBadge from '$lib/components/status-badge.svelte';
	import TagsInput from '$lib/components/tags-input.svelte';
	import {
		Accordion,
		AccordionContent,
		AccordionItem,
		AccordionTrigger,
	} from '$lib/components/ui/accordion';

	let { data } = $props();
	let createOpen = $state(false);
	let vaultTags = $state<string[]>([]);

	let repositories = $state<{ url: string; branch: string; path: string; depth: string; auth_secret_name: string }[]>([]);

	function addRepository() {
		repositories = [...repositories, { url: '', branch: 'main', path: '', depth: '1', auth_secret_name: '' }];
	}

	function removeRepository(index: number) {
		repositories = repositories.filter((_, i) => i !== index);
	}

	let skillRepos = $state<{ repo: string; skill_name: string }[]>([]);

	function addSkillRepo() {
		skillRepos = [...skillRepos, { repo: '', skill_name: '*' }];
	}

	function removeSkillRepo(index: number) {
		skillRepos = skillRepos.filter((_, i) => i !== index);
	}

	const extraParams = data.status ? `&status=${data.status}` : '';

	const { form, errors, enhance, submitting, delayed } = superForm(data.form, {
		applyAction: false,
		invalidateAll: false,
		onResult: ({ result }) => {
			if (result.type === 'success') {
				createOpen = false;
				vaultTags = [];
				toast.success('Session created');
				invalidateAll();
			}
			if (result.type === 'failure') {
				const err = result.data?.error;
				if (err) toast.error(err);
			}
		},
	});

	function truncateId(id: string | null) {
		if (!id) return '-';
		return id.length > 12 ? id.slice(0, 12) : id;
	}
</script>

<ResourceList
	items={data.sessions}
	count={data.count}
	limit={data.limit}
	offset={data.offset}
	title="Sessions"
	description="Manage agent sessions."
	detailHref={(session: any) => `/sessions/${session.id}`}
	archiveAction="?/bulkArchive"
	archiveToast="Sessions archived"
	extraParams={extraParams}
>
	{#snippet createButton()}
		<Button onclick={() => (createOpen = true)}>
			<Plus class="mr-2 h-4 w-4" />
			Create Session
		</Button>
	{/snippet}

	{#snippet filterSlot()}
		<Select.Root
			type="single"
			value={data.status}
			onValueChange={(val) => goto(`?status=${val}&offset=0&limit=${data.limit}`)}
		>
			<Select.Trigger class="w-[180px]">
				<Select.Value placeholder="Filter by status" />
			</Select.Trigger>
			<Select.Content>
				<Select.Item value="" label="All">All</Select.Item>
				<Select.Item value="idle" label="Idle">Idle</Select.Item>
				<Select.Item value="running" label="Running">Running</Select.Item>
				<Select.Item value="creating" label="Creating">Creating</Select.Item>
				<Select.Item value="failed" label="Failed">Failed</Select.Item>
				<Select.Item value="terminated" label="Terminated">Terminated</Select.Item>
			</Select.Content>
		</Select.Root>
	{/snippet}

	{#snippet emptyCreateButton()}
		<button class="underline" onclick={() => (createOpen = true)}>Create your first session</button>.
	{/snippet}

	{#snippet tableHead()}
		<TableHead>Title</TableHead>
		<TableHead>Agent</TableHead>
		<TableHead>Environment</TableHead>
		<TableHead>Status</TableHead>
		<TableHead>Container</TableHead>
		<TableHead>Created</TableHead>
	{/snippet}

	{#snippet tableRow(session: any)}
		<TableCell class="font-medium">
			<a href="/sessions/{session.id}" class="hover:underline">
				{session.title || session.id}
			</a>
		</TableCell>
		<TableCell>
			{data.agentsMap[session.agent_id] || session.agent_id || '-'}
		</TableCell>
		<TableCell>
			{data.envsMap[session.environment_id] || session.environment_id || '-'}
		</TableCell>
		<TableCell>
			<StatusBadge status={session.status} />
		</TableCell>
		<TableCell class="text-muted-foreground font-mono text-xs">
			{truncateId(session.sandbox_container_id)}
		</TableCell>
		<TableCell class="text-muted-foreground">
			{session.created_at ? new Date(session.created_at).toLocaleDateString() : '-'}
		</TableCell>
	{/snippet}
</ResourceList>

<Sheet bind:open={createOpen}>
	<SheetContent class="sm:max-w-md">
		<SheetHeader>
			<SheetTitle>Create Session</SheetTitle>
			<SheetDescription>Select an agent and environment to start a new session.</SheetDescription>
		</SheetHeader>
		<form method="POST" action="?/create" use:enhance class="space-y-4 py-4 px-6">
			<div class="space-y-2">
				<Label for="agent_id">Agent</Label>
				<Select.Root type="single" bind:value={$form.agent_id} name="agent_id">
					<Select.Trigger id="agent_id">
						<Select.Value placeholder="Select an agent" />
					</Select.Trigger>
					<Select.Content>
						{#each data.agents as agent}
							<Select.Item value={agent.id} label={agent.name}>
								{agent.name}
							</Select.Item>
						{/each}
					</Select.Content>
				</Select.Root>
				{#if $errors.agent_id}<p class="text-sm text-destructive">{$errors.agent_id}</p>{/if}
			</div>

			<div class="space-y-2">
				<Label for="environment_id">Environment</Label>
				<Select.Root type="single" bind:value={$form.environment_id} name="environment_id">
					<Select.Trigger id="environment_id">
						<Select.Value placeholder="Select an environment" />
					</Select.Trigger>
					<Select.Content>
						{#each data.environments as env}
							<Select.Item value={env.id} label={env.name}>
								{env.name}
							</Select.Item>
						{/each}
					</Select.Content>
				</Select.Root>
				{#if $errors.environment_id}<p class="text-sm text-destructive">{$errors.environment_id}</p>{/if}
			</div>

			<div class="space-y-2">
				<Label for="title">Title</Label>
				<Input id="title" name="title" bind:value={$form.title} placeholder="Optional title" />
			</div>

			<div class="space-y-2">
				<Label>Vault IDs</Label>
				<TagsInput bind:value={vaultTags} placeholder="Add vault ID and press Enter..." />
				<input type="hidden" name="vault_ids" value={vaultTags.join('\n')} />
			</div>

				<Accordion type="single">
					<AccordionItem value="repositories">
						<AccordionTrigger>Repositories</AccordionTrigger>
					<AccordionContent class="space-y-4 pt-2">
						<div class="space-y-2">
							{#each repositories as repo, i}
								<div class="flex items-start gap-2">
									<div class="flex-1 space-y-1">
										<Input bind:value={repo.url} placeholder="https://github.com/..." />
										<div class="grid grid-cols-2 gap-2 mt-1">
											<Input bind:value={repo.branch} placeholder="branch (default: main)" />
											<Input bind:value={repo.path} placeholder="sub-directory (optional)" />
										</div>
										<div class="grid grid-cols-2 gap-2 mt-1">
											<Input bind:value={repo.depth} placeholder="depth (default: 1)" />
											<Input bind:value={repo.auth_secret_name} placeholder="auth secret name (optional)" />
										</div>
									</div>
									<Button type="button" variant="ghost" size="sm" onclick={() => removeRepository(i)}>
										Remove
									</Button>
								</div>
							{/each}
							<Button type="button" variant="outline" size="sm" onclick={addRepository}>
								Add Repository
							</Button>
						</div>
						<input type="hidden" name="repositories_json" value={JSON.stringify(repositories)} />
					</AccordionContent>
				</AccordionItem>

				<AccordionItem value="skills">
					<AccordionTrigger>Skills</AccordionTrigger>
					<AccordionContent class="space-y-4 pt-2">
						<div class="space-y-2">
							{#each skillRepos as sr, i}
								<div class="flex items-start gap-2">
									<div class="flex-1 space-y-1">
										<Input bind:value={sr.repo} placeholder="GitHub repo (e.g. user/repo)" />
										<Input bind:value={sr.skill_name} placeholder="Skill name or *" class="mt-1" />
									</div>
									<Button type="button" variant="ghost" size="sm" onclick={() => removeSkillRepo(i)}>
										Remove
									</Button>
								</div>
							{/each}
							<Button type="button" variant="outline" size="sm" onclick={addSkillRepo}>
								Add Skill Repo
							</Button>
						</div>
						<input type="hidden" name="skill_repos_json" value={JSON.stringify(skillRepos)} />
					</AccordionContent>
				</AccordionItem>
			</Accordion>

			<Separator />

			<div class="flex items-center gap-2 pt-2">
				<Button type="submit" disabled={$submitting || $delayed}>
					{#if $submitting || $delayed}
						<Loader2 class="mr-2 h-4 w-4 animate-spin" />
						Creating...
					{:else}
						Create Session
					{/if}
				</Button>
				<Button type="button" variant="ghost" onclick={() => (createOpen = false)}>Cancel</Button>
			</div>
		</form>
	</SheetContent>
</Sheet>

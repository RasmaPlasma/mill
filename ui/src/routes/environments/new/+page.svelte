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
	import { Checkbox } from '$lib/components/ui/checkbox';
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
				toast.success('Environment created successfully');
			}
		},
	});

	let skillRepos = $state<{ repo: string; skill_name: string }[]>([]);

	function addSkillRepo() {
		skillRepos = [...skillRepos, { repo: '', skill_name: '*' }];
	}

	function removeSkillRepo(index: number) {
		skillRepos = skillRepos.filter((_, i) => i !== index);
	}

	let repositories = $state<{ url: string; branch: string; path: string; depth: string; auth_secret_name: string }[]>([]);

	function addRepository() {
		repositories = [...repositories, { url: '', branch: 'main', path: '', depth: '1', auth_secret_name: '' }];
	}

	function removeRepository(index: number) {
		repositories = repositories.filter((_, i) => i !== index);
	}
</script>

<div class="space-y-4 max-w-3xl">
	<div class="flex items-center gap-2">
		<Button variant="ghost" size="icon" href="/environments">
			<ArrowLeft class="h-4 w-4" />
		</Button>
		<div>
			<h2 class="text-2xl font-bold tracking-tight">Create Environment</h2>
			<p class="text-muted-foreground">Configure a new sandbox environment.</p>
		</div>
	</div>

	<Card>
		<CardHeader>
			<CardTitle>Environment Configuration</CardTitle>
			<CardDescription>Define packages, networking, and resource limits.</CardDescription>
		</CardHeader>
		<CardContent>
			<form method="POST" use:enhance class="space-y-6">
				<div class="space-y-2">
					<Label for="name">Name</Label>
					<Input id="name" name="name" bind:value={$form.name} placeholder="my-environment" />
					{#if $errors.name}<p class="text-sm text-destructive">{$errors.name}</p>{/if}
				</div>

				<div class="space-y-2">
					<Label for="base_image">Base Image (optional)</Label>
					<Input id="base_image" name="base_image" bind:value={$form.base_image} placeholder="e.g. ubuntu:24.04 or deepagents/sandbox-base:latest" />
					{#if $errors.base_image}<p class="text-sm text-destructive">{$errors.base_image}</p>{/if}
				</div>

				<Accordion type="single" value="packages">
					<AccordionItem value="packages">
						<AccordionTrigger>Packages</AccordionTrigger>
						<AccordionContent class="space-y-4 pt-2">
							<div class="space-y-2">
								<Label for="packages_pip">pip packages (space or comma separated)</Label>
								<Textarea id="packages_pip" name="packages_pip" bind:value={$form.packages_pip} placeholder="requests numpy pandas" rows={2} />
							</div>
							<div class="space-y-2">
								<Label for="packages_npm">npm packages (space or comma separated)</Label>
								<Textarea id="packages_npm" name="packages_npm" bind:value={$form.packages_npm} placeholder="lodash axios" rows={2} />
							</div>
							<div class="space-y-2">
								<Label for="packages_apt">apt packages (space or comma separated)</Label>
								<Textarea id="packages_apt" name="packages_apt" bind:value={$form.packages_apt} placeholder="curl jq" rows={2} />
							</div>
						</AccordionContent>
					</AccordionItem>

					<AccordionItem value="networking">
						<AccordionTrigger>Networking</AccordionTrigger>
						<AccordionContent class="space-y-4 pt-2">
							<div class="space-y-2">
								<Label for="networking_type">Type</Label>
								<select
									id="networking_type"
									name="networking_type"
									bind:value={$form.networking_type}
									class="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
								>
									<option value="limited">limited</option>
									<option value="open">open</option>
								</select>
							</div>
							<div class="space-y-2">
								<Label for="networking_allowed_hosts">Allowed Hosts (space or comma separated)</Label>
								<Textarea id="networking_allowed_hosts" name="networking_allowed_hosts" bind:value={$form.networking_allowed_hosts} placeholder="pypi.org npmjs.com" rows={2} />
							</div>
							<div class="flex items-center gap-2">
								<Checkbox id="networking_allow_package_managers" name="networking_allow_package_managers" bind:checked={$form.networking_allow_package_managers} />
								<Label for="networking_allow_package_managers" class="font-normal">Allow package managers</Label>
							</div>
						</AccordionContent>
					</AccordionItem>

					<AccordionItem value="resources">
						<AccordionTrigger>Resource Limits</AccordionTrigger>
						<AccordionContent class="space-y-4 pt-2">
							<div class="space-y-2">
								<Label for="resource_memory">Memory</Label>
								<Input id="resource_memory" name="resource_memory" bind:value={$form.resource_memory} placeholder="1g" />
							</div>
							<div class="space-y-2">
								<Label for="resource_cpus">CPUs</Label>
								<Input id="resource_cpus" name="resource_cpus" type="number" step="0.1" bind:value={$form.resource_cpus} />
							</div>
							<div class="space-y-2">
								<Label for="resource_pids_limit">PIDs Limit</Label>
								<Input id="resource_pids_limit" name="resource_pids_limit" type="number" bind:value={$form.resource_pids_limit} />
							</div>
						</AccordionContent>
					</AccordionItem>

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

				<div class="flex items-center gap-4 pt-4">
					<Button type="submit" disabled={$submitting || $delayed}>
						{#if $submitting || $delayed}
							<Loader2 class="mr-2 h-4 w-4 animate-spin" />
							Creating...
						{:else}
							Create Environment
						{/if}
					</Button>
					<Button type="button" variant="outline" href="/environments">Cancel</Button>
				</div>
			</form>
		</CardContent>
	</Card>
</div>

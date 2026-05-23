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
	import { Checkbox } from '$lib/components/ui/checkbox';
	import { Separator } from '$lib/components/ui/separator';
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

	let skillRepos = $state<{ repo: string; skill_name: string }[]>(
		(data.env.skill_repos || []).map((sr: any) => ({ repo: sr.repo || '', skill_name: sr.skill_name || '*' }))
	);

	function addSkillRepo() {
		skillRepos = [...skillRepos, { repo: '', skill_name: '*' }];
	}

	function removeSkillRepo(index: number) {
		skillRepos = skillRepos.filter((_, i) => i !== index);
	}

	let repositories = $state<{ url: string; branch: string; path: string; depth: string; auth_secret_name: string }[]>(
		(data.env.repositories || []).map((r: any) => ({
			url: r.url || '',
			branch: r.branch || 'main',
			path: r.path || '',
			depth: r.depth != null ? String(r.depth) : '1',
			auth_secret_name: r.auth_secret_name || '',
		}))
	);

	function addRepository() {
		repositories = [...repositories, { url: '', branch: 'main', path: '', depth: '1', auth_secret_name: '' }];
	}

	function removeRepository(index: number) {
		repositories = repositories.filter((_, i) => i !== index);
	}

	function formatDate(d: string | null) {
		if (!d) return '-';
		return new Date(d).toLocaleString();
	}

	function packageSummary(packages: Record<string, string[]>) {
		const counts: string[] = [];
		if (packages?.pip?.length) counts.push(`${packages.pip.length} pip`);
		if (packages?.npm?.length) counts.push(`${packages.npm.length} npm`);
		if (packages?.apt?.length) counts.push(`${packages.apt.length} apt`);
		return counts.length ? counts.join(', ') : '-';
	}
</script>

<div class="space-y-4 max-w-3xl">
	<div class="flex items-center justify-between">
		<div class="flex items-center gap-2">
			<Button variant="ghost" size="icon" href="/environments">
				<ArrowLeft class="h-4 w-4" />
			</Button>
			<div>
				<h2 class="text-2xl font-bold tracking-tight">{data.env.name}</h2>
				<p class="text-muted-foreground flex items-center gap-2">
					<Badge variant="outline">{data.env.networking?.type || 'limited'}</Badge>
					{#if data.env.base_image}
						<Badge variant="secondary">{data.env.base_image}</Badge>
					{/if}
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
					<AlertDialogTitle>Archive Environment</AlertDialogTitle>
					<AlertDialogDescription>
						This will archive the environment "{data.env.name}". It will no longer appear in lists or be usable in new sessions.
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
					<div class="grid grid-cols-[140px_1fr] gap-2 text-sm">
						<span class="text-muted-foreground">Name</span>
						<span class="font-medium">{data.env.name}</span>

						<span class="text-muted-foreground">Base Image</span>
						<span class="font-medium">{data.env.base_image || '-'}</span>

						<span class="text-muted-foreground">Packages</span>
						<span>{packageSummary(data.env.packages)}</span>

						<span class="text-muted-foreground">Networking</span>
						<span>
							<Badge variant="outline">{data.env.networking?.type || 'limited'}</Badge>
							{#if data.env.networking?.allow_package_managers}
								<Badge variant="secondary">package managers allowed</Badge>
							{/if}
						</span>

						<span class="text-muted-foreground">Allowed Hosts</span>
						<span class="text-muted-foreground">
							{(data.env.networking?.allowed_hosts ?? []).join(', ') || '-'}
						</span>

						<span class="text-muted-foreground">Resources</span>
						<span>
							Memory: {data.env.resource_limits?.memory || '-'},
							CPUs: {data.env.resource_limits?.cpus || '-'},
							PIDs: {data.env.resource_limits?.pids_limit || '-'}
						</span>

						<span class="text-muted-foreground">IP Subnet</span>
						<span class="font-medium">{data.env.ip_subnet || '-'}</span>

						<span class="text-muted-foreground">Created</span>
						<span class="text-muted-foreground">{formatDate(data.env.created_at)}</span>

						<span class="text-muted-foreground">Updated</span>
						<span class="text-muted-foreground">{formatDate(data.env.updated_at)}</span>
					</div>

					{#if data.env.repositories && data.env.repositories.length > 0}
						<Separator />
						<div class="space-y-2">
							<span class="text-sm font-medium">Repositories</span>
							<div class="space-y-2">
								{#each data.env.repositories as repo}
									<div class="rounded-md border p-3 text-sm">
										<div class="font-medium">{repo.url}</div>
										<div class="text-muted-foreground">
											branch: {repo.branch || 'main'}
											{#if repo.path} | path: {repo.path}{/if}
											{#if repo.auth_secret_name} | auth: {repo.auth_secret_name}{/if}
										</div>
									</div>
								{/each}
							</div>
						</div>
					{/if}

					{#if data.env.skill_repos && data.env.skill_repos.length > 0}
						<Separator />
						<div class="space-y-2">
							<span class="text-sm font-medium">Skill Repos</span>
							<div class="space-y-2">
								{#each data.env.skill_repos as sr}
									<div class="rounded-md border p-3 text-sm">
										<div class="font-medium">{sr.repo}</div>
										<div class="text-muted-foreground">skill: {sr.skill_name || '*'}</div>
									</div>
								{/each}
							</div>
						</div>
					{/if}
				</CardContent>
			</Card>
		</TabsContent>

		<TabsContent value="edit">
			<Card>
				<CardHeader>
					<CardTitle>Edit Environment</CardTitle>
					<CardDescription>Update environment configuration.</CardDescription>
				</CardHeader>
				<CardContent>
					<form method="POST" action="?/update" use:enhance class="space-y-6">
						<div class="space-y-2">
							<Label for="name">Name</Label>
							<Input id="name" name="name" bind:value={$form.name} />
							{#if $errors.name}<p class="text-sm text-destructive">{$errors.name}</p>{/if}
						</div>

						<div class="space-y-2">
							<Label for="base_image">Base Image</Label>
							<Input id="base_image" name="base_image" bind:value={$form.base_image} placeholder="e.g. ubuntu:24.04" />
						</div>

						<Accordion type="single" value="packages">
							<AccordionItem value="packages">
								<AccordionTrigger>Packages</AccordionTrigger>
								<AccordionContent class="space-y-4 pt-2">
									<div class="space-y-2">
										<Label for="packages_pip">pip packages</Label>
										<Textarea id="packages_pip" name="packages_pip" bind:value={$form.packages_pip} rows={2} />
									</div>
									<div class="space-y-2">
										<Label for="packages_npm">npm packages</Label>
										<Textarea id="packages_npm" name="packages_npm" bind:value={$form.packages_npm} rows={2} />
									</div>
									<div class="space-y-2">
										<Label for="packages_apt">apt packages</Label>
										<Textarea id="packages_apt" name="packages_apt" bind:value={$form.packages_apt} rows={2} />
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
										<Label for="networking_allowed_hosts">Allowed Hosts</Label>
										<Textarea id="networking_allowed_hosts" name="networking_allowed_hosts" bind:value={$form.networking_allowed_hosts} rows={2} />
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
										<Input id="resource_memory" name="resource_memory" bind:value={$form.resource_memory} />
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
									Saving...
								{:else}
									Save Changes
								{/if}
							</Button>
							<Button type="button" variant="outline" href="/environments">Cancel</Button>
						</div>
					</form>
				</CardContent>
			</Card>
		</TabsContent>
	</Tabs>
</div>

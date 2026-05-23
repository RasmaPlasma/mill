<script lang="ts">
	import { FolderOpen } from 'lucide-svelte';

	let { output = '' }: { output?: string } = $props();

	function parseLsOutput(str: string): string[] | null {
		try {
			// Python repr to JSON: replace single quotes with double quotes
			// But be careful with apostrophes inside strings
			const jsonLike = str.replace(/'/g, '"');
			const parsed = JSON.parse(jsonLike);
			if (Array.isArray(parsed)) return parsed;
			return null;
		} catch {
			return null;
		}
	}

	const paths = $derived(parseLsOutput(output));
</script>

<div class="rounded border bg-muted/30 overflow-hidden">
	<div class="flex items-center gap-2 px-2.5 py-1.5 border-b bg-muted/50">
		<FolderOpen class="h-3.5 w-3.5 text-muted-foreground" />
		<span class="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">Directory</span>
	</div>
	<div class="px-3 py-2">
		{#if paths}
			<ul class="space-y-0.5">
				{#each paths as path}
					<li class="text-xs font-mono text-foreground flex items-center gap-1.5">
						<FolderOpen class="h-3 w-3 text-muted-foreground shrink-0" />
						<span class="truncate">{path}</span>
					</li>
				{/each}
			</ul>
		{:else}
			<pre class="text-xs font-mono text-foreground whitespace-pre-wrap">{output}</pre>
		{/if}
	</div>
</div>

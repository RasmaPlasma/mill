<script lang="ts">
	import { Terminal, CheckCircle2, XCircle } from 'lucide-svelte';

	let { output = '' }: { output?: string } = $props();

	function parseExecuteOutput(str: string): { stdout: string; exitCode: number | null; isError: boolean } {
		const match = str.match(/\[Command (succeeded|failed) with exit code (\d+)\]$/);
		if (match) {
			const isError = match[1] === 'failed';
			const exitCode = parseInt(match[2], 10);
			const stdout = str.slice(0, str.lastIndexOf(match[0])).trimEnd();
			return { stdout, exitCode, isError };
		}
		return { stdout: str, exitCode: null, isError: false };
	}

	const result = $derived(parseExecuteOutput(output));
	let expanded = $state(false);
</script>

<div class="rounded border bg-muted/30 overflow-hidden">
	<div class="flex items-center gap-2 px-2.5 py-1.5 border-b bg-muted/50">
		<Terminal class="h-3.5 w-3.5 text-muted-foreground" />
		<span class="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">Output</span>
		{#if result.exitCode !== null}
			<span class="inline-flex items-center gap-1 ml-auto text-[10px] font-medium {result.isError ? 'text-red-600' : 'text-green-600'}">
				{#if result.isError}
					<XCircle class="h-3 w-3" />
				{:else}
					<CheckCircle2 class="h-3 w-3" />
				{/if}
				exit {result.exitCode}
			</span>
		{/if}
	</div>
	<div class="px-3 py-2">
		{#if result.stdout}
			<pre class="text-xs font-mono leading-relaxed text-foreground whitespace-pre-wrap break-all {result.stdout.length > 2000 && !expanded ? 'max-h-[200px] overflow-hidden mask-bottom' : ''}">{result.stdout}</pre>
			{#if result.stdout.length > 2000 && !expanded}
				<button
					class="mt-1.5 text-[10px] text-primary hover:underline"
					onclick={() => expanded = true}
				>
					Show full output ({result.stdout.length.toLocaleString()} chars)
				</button>
			{/if}
		{:else}
			<div class="text-xs text-muted-foreground italic">No output</div>
		{/if}
	</div>
</div>

<style>
	.mask-bottom {
		mask-image: linear-gradient(to bottom, black 70%, transparent 100%);
		-webkit-mask-image: linear-gradient(to bottom, black 70%, transparent 100%);
	}
</style>

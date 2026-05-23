<script lang="ts">
	import { Terminal } from 'lucide-svelte';

	let { command = '', timeout }: { command?: string; timeout?: number } = $props();
</script>

<div class="rounded border bg-muted/30 overflow-hidden">
	<div class="flex items-center gap-2 px-2.5 py-1.5 border-b bg-muted/50">
		<Terminal class="h-3.5 w-3.5 text-muted-foreground" />
		<span class="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">Shell</span>
		{#if timeout}
			<span class="text-[10px] text-muted-foreground ml-auto">timeout: {timeout}s</span>
		{/if}
	</div>
	<pre class="px-3 py-2 text-xs font-mono leading-relaxed text-foreground whitespace-pre-wrap break-all"><span class="text-muted-foreground select-none">$ </span>{command}</pre>
</div>

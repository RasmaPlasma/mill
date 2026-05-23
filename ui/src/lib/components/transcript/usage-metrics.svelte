<script lang="ts">
	import { BarChart3 } from 'lucide-svelte';

	let { usage }: { usage?: { input_tokens?: number; output_tokens?: number; total_tokens?: number; cache_read_tokens?: number; cache_write_tokens?: number } } = $props();

	const input = $derived(usage?.input_tokens || 0);
	const output = $derived(usage?.output_tokens || 0);
	const total = $derived(usage?.total_tokens || 0);
	const cacheRead = $derived(usage?.cache_read_tokens || 0);
	const cacheWrite = $derived(usage?.cache_write_tokens || 0);
</script>

<div class="inline-flex items-center gap-2 px-2 py-1 rounded text-[10px] font-medium border bg-amber-500/10 text-amber-700 border-amber-500/20">
	<BarChart3 class="h-3 w-3" />
	<span>{input.toLocaleString()} &rarr; {output.toLocaleString()} tokens</span>
	{#if total}<span class="text-muted-foreground">&middot; {total.toLocaleString()} total</span>{/if}
	{#if cacheRead}<span class="text-muted-foreground">&middot; {cacheRead.toLocaleString()} cache read</span>{/if}
	{#if cacheWrite}<span class="text-muted-foreground">&middot; {cacheWrite.toLocaleString()} cache write</span>{/if}
</div>

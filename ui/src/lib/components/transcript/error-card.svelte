<script lang="ts">
	import { AlertCircle } from 'lucide-svelte';

	let { error }: { error?: { type?: string; message?: string; retry_status?: string } } = $props();

	const type = $derived(error?.type || 'error');
	const message = $derived(error?.message || 'Unknown error');
	const retryStatus = $derived(error?.retry_status || '');
</script>

<div class="rounded border border-red-500/20 bg-red-500/5 p-3">
	<div class="flex items-start gap-2">
		<AlertCircle class="h-4 w-4 text-red-500 shrink-0 mt-0.5" />
		<div class="min-w-0">
			<div class="flex items-center gap-2 mb-1">
				<span class="text-xs font-medium text-red-600">{type}</span>
				{#if retryStatus}
					<span class="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium border bg-red-500/10 text-red-600 border-red-500/20">
						{retryStatus}
					</span>
				{/if}
			</div>
			<p class="text-xs text-red-700/80 leading-relaxed">{message}</p>
		</div>
	</div>
</div>

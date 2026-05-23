<script lang="ts">
	import { Play, Square } from 'lucide-svelte';

	let { status, stopReason }: { status: 'running' | 'idle'; stopReason?: string } = $props();
</script>

{#if status === 'running'}
	<div class="inline-flex items-center gap-1.5 px-2 py-1 rounded text-[10px] font-medium border bg-blue-500/10 text-blue-600 border-blue-500/20">
		<Play class="h-3 w-3" />
		Running
	</div>
{:else}
	<div class="inline-flex items-center gap-1.5 px-2 py-1 rounded text-[10px] font-medium border bg-gray-500/10 text-gray-600 border-gray-500/20">
		<Square class="h-3 w-3" />
		Idle{#if stopReason}&nbsp;&middot;&nbsp;{stopReason}{/if}
	</div>
{/if}

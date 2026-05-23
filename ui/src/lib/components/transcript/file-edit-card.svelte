<script lang="ts">
	import { FileDiff } from 'lucide-svelte';

	let {
		filePath = '',
		oldString = '',
		newString = '',
	}: {
		filePath?: string;
		oldString?: string;
		newString?: string;
	} = $props();
</script>

<div class="rounded border bg-muted/30 overflow-hidden">
	<div class="flex items-center gap-2 px-2.5 py-1.5 border-b bg-muted/50">
		<FileDiff class="h-3.5 w-3.5 text-muted-foreground" />
		<span class="text-[10px] font-medium text-muted-foreground font-mono truncate">{filePath}</span>
	</div>
	<div class="grid grid-cols-1 gap-px bg-border">
		<div class="bg-red-500/5 px-3 py-2">
			<div class="text-[10px] font-medium text-red-600 mb-1">Before</div>
			<pre class="text-xs font-mono leading-relaxed text-foreground whitespace-pre-wrap break-all">{oldString}</pre>
		</div>
		<div class="bg-green-500/5 px-3 py-2">
			<div class="text-[10px] font-medium text-green-600 mb-1">After</div>
			<pre class="text-xs font-mono leading-relaxed text-foreground whitespace-pre-wrap break-all">{newString}</pre>
		</div>
	</div>
</div>

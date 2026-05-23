<script lang="ts">
	import { FileText } from 'lucide-svelte';

	let { filePath = '', content = '' }: { filePath?: string; content?: string } = $props();

	// read_file output already has line numbers from the backend:
	//      1  content
	//    102  content
	// We render it raw without adding our own line numbers
</script>

<div class="rounded border bg-muted/30 overflow-hidden">
	<div class="flex items-center gap-2 px-2.5 py-1.5 border-b bg-muted/50">
		<FileText class="h-3.5 w-3.5 text-muted-foreground" />
		<span class="text-[10px] font-medium text-muted-foreground font-mono truncate">{filePath}</span>
	</div>
	<pre class="px-3 py-2 text-xs font-mono leading-relaxed text-foreground overflow-x-auto max-h-[400px]">{content}</pre>
</div>

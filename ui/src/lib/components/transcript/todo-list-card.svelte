<script lang="ts">
	import { ListChecks } from 'lucide-svelte';

	interface Todo {
		status: string;
		content: string;
	}

	let { output = '' }: { output?: string } = $props();

	function parseTodoOutput(str: string): Todo[] | null {
		try {
			// Extract the array part: "Updated todo list to [{...}]"
			const match = str.match(/\[.*\]/s);
			if (!match) return null;
			const jsonLike = match[0].replace(/'/g, '"');
			const parsed = JSON.parse(jsonLike);
			if (Array.isArray(parsed)) return parsed;
			return null;
		} catch {
			return null;
		}
	}

	function statusBadgeClass(status: string): string {
		switch (status) {
			case 'completed':
				return 'bg-green-500/15 text-green-600 border-green-500/20';
			case 'in_progress':
				return 'bg-amber-500/15 text-amber-600 border-amber-500/20';
			case 'pending':
				return 'bg-gray-500/15 text-gray-500 border-gray-500/20';
			default:
				return 'bg-gray-500/15 text-gray-500 border-gray-500/20';
		}
	}

	const todos = $derived(parseTodoOutput(output));
</script>

<div class="rounded border bg-muted/30 overflow-hidden">
	<div class="flex items-center gap-2 px-2.5 py-1.5 border-b bg-muted/50">
		<ListChecks class="h-3.5 w-3.5 text-muted-foreground" />
		<span class="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">Todos</span>
	</div>
	<div class="px-3 py-2">
		{#if todos}
			<ul class="space-y-1.5">
				{#each todos as todo}
					<li class="flex items-start gap-2">
						<span class="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium border shrink-0 mt-0.5 {statusBadgeClass(todo.status)}">
							{todo.status}
						</span>
						<span class="text-xs text-foreground">{todo.content}</span>
					</li>
				{/each}
			</ul>
		{:else}
			<pre class="text-xs font-mono text-foreground whitespace-pre-wrap">{output}</pre>
		{/if}
	</div>
</div>
